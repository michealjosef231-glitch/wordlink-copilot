"""One-worker live screen reader. It never sends gameplay input."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from queue import Empty, Queue
from threading import Event, Lock, Thread, current_thread
from time import monotonic, perf_counter

import cv2
import numpy as np

from wordlink.capture.sources import (
    CaptureError,
    CapturedFrame,
    CapturePermissionError,
    FrameSource,
    SourceUnavailable,
)
from wordlink.capture.video import SettleDetector
from wordlink.model import Box, Recognition
from wordlink.solver.ranking import RankedWord, rank_words
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.vocabulary.policy import VocabularyPolicy
from wordlink.vision.board import recognize
from wordlink.vision.dots import count_dots
from wordlink.vision.letters import extract_glyph
from wordlink.vision.tiles import detect_tiles

MAX_PROCESSING_DIMENSION = 1024


@dataclass(frozen=True)
class LiveConfig:
    sample_fps: float = 4.0
    quiet_frames: int = 3
    # A detected grid edge can shift one codec pixel between adjacent frames;
    # that alone yields ~0.014 mean board-crop difference in the reference
    # recording even while all sixteen tiles are unchanged.
    threshold: float = 0.018
    max_frame_age: float = 1.5

    def __post_init__(self) -> None:
        for name in ("sample_fps", "threshold", "max_frame_age"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        if self.sample_fps > 60:
            raise ValueError("sample_fps cannot exceed 60")
        if self.threshold > 1:
            raise ValueError("threshold must be a normalized image difference at most 1")
        if isinstance(self.quiet_frames, bool) or not isinstance(self.quiet_frames, int) or self.quiet_frames < 2:
            raise ValueError("quiet_frames must be an integer of at least 2")


@dataclass(frozen=True)
class LiveUpdate:
    state: str
    message: str
    frame: CapturedFrame | None = None
    recognition: Recognition | None = None
    ranked_words: tuple[RankedWord, ...] = ()
    elapsed_ms: float = 0
    solve_ms: float = 0
    sequence: int = 0


def _prepare_frame(frame: CapturedFrame) -> CapturedFrame:
    image = frame.image
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise CaptureError("The source must supply a uint8 BGR image with three channels")
    if min(image.shape[:2]) < 40:
        raise CaptureError("The captured image is too small to contain a readable board")
    height, width = image.shape[:2]
    if max(height, width) > MAX_PROCESSING_DIMENSION:
        ratio = MAX_PROCESSING_DIMENSION / max(height, width)
        image = cv2.resize(image, (round(width * ratio), round(height * ratio)), interpolation=cv2.INTER_AREA)
    else:
        # Sources can lend native/replay buffers. Keep the displayed frame
        # independent of the source's next read on this same worker.
        image = image.copy()
    image.setflags(write=False)
    return CapturedFrame(image, frame.captured_at, frame.media_time)


def _board_crop(image: np.ndarray, boxes: tuple[Box, ...]) -> np.ndarray:
    if len(boxes) != 16:
        raise ValueError("A complete 4x4 tile grid is required")
    x1, y1 = min(box[0] for box in boxes), min(box[1] for box in boxes)
    x2 = max(box[0] + box[2] for box in boxes)
    y2 = max(box[1] + box[3] for box in boxes)
    if x1 < 0 or y1 < 0 or x2 > image.shape[1] or y2 > image.shape[0] or x2 <= x1 or y2 <= y1:
        raise ValueError("Detected tile bounds extend outside the captured image")
    return image[y1:y2, x1:x2]


@dataclass(frozen=True)
class _ContentSignature:
    boxes: tuple[Box, ...]
    glyphs: tuple[np.ndarray, ...]
    dots: tuple[int, ...]
    uncertain_dots: tuple[bool, ...]


def _content_fingerprint(image: np.ndarray, boxes: tuple[Box, ...]) -> _ContentSignature:
    """Describe tile ink without treating video compression as board motion.

    A one-pixel shift in a detected edge changes a cryptographic hash on every
    recorded frame. Normalized glyphs permit a small shape tolerance while
    exact dot counts still catch changes too small for the global motion test.
    """
    glyphs = []
    dots = []
    uncertain_dots = []
    for x, y, width, height in boxes:
        tile = image[y:y + height, x:x + width]
        glyphs.append(extract_glyph(tile))
        dot_count, quality = count_dots(tile)
        dots.append(dot_count)
        uncertain_dots.append(quality < .65)
    return _ContentSignature(boxes, tuple(glyphs), tuple(dots), tuple(uncertain_dots))


def _same_content(previous: _ContentSignature | bytes, current: _ContentSignature | bytes) -> bool:
    # A few tests inject a constant opaque signature to isolate lifecycle
    # behavior; real captures always use _ContentSignature.
    if not isinstance(previous, _ContentSignature) or not isinstance(current, _ContentSignature):
        return previous == current
    if previous.dots != current.dots or previous.uncertain_dots != current.uncertain_dots:
        return False
    # A substantial window resize must refresh the stored path coordinates.
    if any(max(abs(old - new) for old, new in zip(a, b)) > 3
           for a, b in zip(previous.boxes, current.boxes)):
        return False
    return all(np.count_nonzero(a != b) / a.size < .02
               for a, b in zip(previous.glyphs, current.glyphs))


def _structure_changed(previous: _ContentSignature | bytes, current: _ContentSignature | bytes) -> bool:
    if not isinstance(previous, _ContentSignature) or not isinstance(current, _ContentSignature):
        return False
    return (previous.dots != current.dots
            or previous.uncertain_dots != current.uncertain_dots
            or any(max(abs(old - new) for old, new in zip(a, b)) > 3
                   for a, b in zip(previous.boxes, current.boxes)))


class LiveAssistant:
    """Read a selected source, settle its detected board, and suggest locally.

    A controller owns one source and is single-use after it ends or stops.
    Sources must finish each read in finite time. Cancellation is immediate for
    published suggestions; resource cleanup happens on the worker after read
    finishes, so read and close never access native buffers concurrently.
    """

    def __init__(self, source: FrameSource, trie: Trie, policy: VocabularyPolicy, config: LiveConfig | None = None) -> None:
        self.source = source
        self.trie = trie
        self.policy = policy
        self.config = config or LiveConfig()
        self._stop = Event()
        self._lifecycle_lock = Lock()
        self._update_lock = Lock()
        self._close_lock = Lock()
        self._updates: Queue[LiveUpdate] = Queue(maxsize=1)
        self._last_update: LiveUpdate | None = None
        self._sequence = 0
        self._thread: Thread | None = None
        self._started = False
        self._source_closed = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self.is_running:
                return
            if self._started or self._source_closed:
                raise RuntimeError("This live assistant has finished; start with a fresh source")
            self._started = True
            self._publish(LiveUpdate("waiting", f"Waiting for a settled 4x4 board from {self.source.label}"))
            self._thread = Thread(target=self._run, name="wordlink-live-reader", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 0.5) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Stop timeout must be a finite nonnegative number")
        with self._lifecycle_lock:
            self._stop.set()
            self._publish(LiveUpdate("stopped", "Live reading stopped"))
            worker = self._thread
            if worker is None:
                self._started = True
                cleanup_error = self._close_source()
                if cleanup_error:
                    self._publish(LiveUpdate("stopped", f"Live reading stopped; cleanup failed: {cleanup_error}"))
        if worker is not None and worker is not current_thread():
            worker.join(timeout)

    def poll(self) -> LiveUpdate | None:
        with self._update_lock:
            try:
                update = self._updates.get_nowait()
            except Empty:
                update = None
            latest = update or self._last_update
            # This also expires an already consumed heartbeat while a backend
            # read is slow; the GUI need not wait for another capture to clear.
            if latest is not None and latest.state == "ready" and not self._fresh(latest.frame):
                self._sequence += 1
                expired = LiveUpdate("waiting", "Capture is stale; waiting for a fresh frame", sequence=self._sequence)
                self._last_update = expired
                return expired
            return update

    def _fresh(self, frame: CapturedFrame | None) -> bool:
        if frame is None or isinstance(frame.captured_at, bool) or not isinstance(frame.captured_at, (int, float)):
            return False
        age = monotonic() - frame.captured_at
        return math.isfinite(age) and 0 <= age <= self.config.max_frame_age

    def _publish(self, update: LiveUpdate) -> None:
        with self._update_lock:
            if self._stop.is_set() and update.state != "stopped":
                return
            self._sequence += 1
            update = replace(update, sequence=self._sequence)
            self._last_update = update
            try:
                self._updates.get_nowait()
            except Empty:
                pass
            self._updates.put_nowait(update)

    def _close_source(self) -> str | None:
        with self._close_lock:
            if self._source_closed:
                return None
            self._source_closed = True
        try:
            self.source.close()
        except Exception as exc:
            return str(exc) or type(exc).__name__
        return None

    def _run(self) -> None:
        detector = SettleDetector(self.config.quiet_frames, self.config.threshold)
        fingerprint: _ContentSignature | bytes | None = None
        cached_fingerprint: _ContentSignature | bytes | None = None
        cached_read: Recognition | None = None
        cached_ranked: tuple[RankedWord, ...] = ()
        solved_identity: tuple[tuple[str, ...], tuple[int, ...]] | None = None
        solved_ranked: tuple[RankedWord, ...] = ()
        interval = 1 / self.config.sample_fps

        def invalidate() -> None:
            nonlocal detector, fingerprint, cached_fingerprint, cached_read, cached_ranked
            detector = SettleDetector(self.config.quiet_frames, self.config.threshold)
            fingerprint = None
            cached_fingerprint = None
            cached_read = None
            cached_ranked = ()

        try:
            while not self._stop.is_set():
                started = perf_counter()
                raw = self.source.read()
                if self._stop.is_set():
                    break
                if raw is None:
                    self._publish(LiveUpdate("ended", "The selected recording has ended"))
                    break
                if not self._fresh(raw):
                    invalidate()
                    self._publish(LiveUpdate("waiting", "Capture is stale; waiting for a fresh frame"))
                    self._stop.wait(max(0, interval - (perf_counter() - started)))
                    continue
                frame = _prepare_frame(raw)
                try:
                    boxes = detect_tiles(frame.image)
                    crop = _board_crop(frame.image, boxes)
                except ValueError as exc:
                    invalidate()
                    self._publish(LiveUpdate("waiting", f"Waiting for a complete board: {exc}", frame))
                    self._stop.wait(max(0, interval - (perf_counter() - started)))
                    continue
                try:
                    current_fingerprint = _content_fingerprint(frame.image, boxes)
                except ValueError as exc:
                    invalidate()
                    self._publish(LiveUpdate("review", f"Tile content needs review: {exc}", frame))
                    self._stop.wait(max(0, interval - (perf_counter() - started)))
                    continue
                # Cache tolerances must be measured from the recognized frame.
                # Comparing only adjacent captures lets small changes accumulate
                # indefinitely while old letters and path coordinates survive.
                baseline = cached_fingerprint if cached_read is not None else fingerprint
                content_changed = baseline is not None and not _same_content(baseline, current_fingerprint)
                structural_change = baseline is not None and _structure_changed(baseline, current_fingerprint)
                previous_identity = None
                verifying_ready = False
                if structural_change:
                    invalidate()
                elif content_changed and cached_read is not None:
                    # A selected/highlighted tile can alter the normalized
                    # glyph every frame without changing its letter. Verify
                    # semantics instead of restarting the settle timer on
                    # every codec/selection fluctuation.
                    previous_identity = (cached_read.board.letters, cached_read.board.dots)
                    verifying_ready = not cached_read.warnings
                    cached_read = None
                    cached_fingerprint = None
                    cached_ranked = ()
                fingerprint = current_fingerprint
                settled_now = detector.update(crop)
                if detector.quiet_count < self.config.quiet_frames:
                    cached_read = None
                    cached_fingerprint = None
                    cached_ranked = ()
                    self._publish(LiveUpdate("waiting", "Board is moving; waiting for quiet frames", frame))
                elif settled_now or cached_read is None:
                    # Quiet selection/codec ink often verifies to the same
                    # board. Keep its last confident update visible during
                    # that internal check instead of flashing empty results.
                    # Its timestamp is not renewed: poll() still expires it
                    # if verification stalls. Motion, changed semantics and
                    # uncertainty publish their clearing states below.
                    if not verifying_ready:
                        self._publish(LiveUpdate("reading", "Reading letters and dots on the settled board", frame))
                    try:
                        read = recognize(frame.image)
                    except ValueError as exc:
                        invalidate()
                        self._publish(LiveUpdate("review", f"Board needs review: {exc}", frame))
                        self._stop.wait(max(0, interval - (perf_counter() - started)))
                        continue
                    if self._stop.is_set():
                        break
                    if not self._fresh(frame):
                        invalidate()
                        self._publish(LiveUpdate("waiting", "Capture became stale while reading; waiting for a fresh frame"))
                        self._stop.wait(max(0, interval - (perf_counter() - started)))
                        continue
                    if (previous_identity is not None
                            and (read.board.letters, read.board.dots) != previous_identity):
                        # A genuine letter change deserves a new quiet period
                        # before any candidate for the new board is shown.
                        invalidate()
                        fingerprint = current_fingerprint
                        detector.update(crop)
                        self._publish(LiveUpdate("waiting", "Board changed; waiting for quiet frames", frame))
                        self._stop.wait(max(0, interval - (perf_counter() - started)))
                        continue
                    cached_read = read
                    cached_fingerprint = current_fingerprint
                    solve_ms = 0.0
                    if read.warnings:
                        cached_ranked = ()
                    else:
                        identity = (read.board.letters, read.board.dots)
                        if identity != solved_identity:
                            solving = perf_counter()
                            solved_ranked = tuple(rank_words(find_words(read.board, self.trie), self.policy))
                            solve_ms = (perf_counter() - solving) * 1000
                            solved_identity = identity
                        cached_ranked = solved_ranked
                    if self._stop.is_set():
                        break
                    if not self._fresh(frame):
                        invalidate()
                        self._publish(LiveUpdate("waiting", "Capture became stale while solving; waiting for a fresh frame"))
                    else:
                        self._publish_read(frame, cached_read, cached_ranked, started, solve_ms)
                else:
                    # New capture timestamp, cached OCR, current source image.
                    if self._fresh(frame):
                        self._publish_read(frame, cached_read, cached_ranked, started, 0.0)
                    else:
                        invalidate()
                        self._publish(LiveUpdate("waiting", "Capture is stale; waiting for a fresh frame"))
                self._stop.wait(max(0, interval - (perf_counter() - started)))
        except (CapturePermissionError, PermissionError) as exc:
            self._publish(LiveUpdate("permission", f"Screen Recording permission is required: {exc}"))
        except SourceUnavailable as exc:
            self._publish(LiveUpdate("disconnected", f"The selected source disconnected: {exc}"))
        except Exception as exc:
            self._publish(LiveUpdate("error", f"Live reading failed: {str(exc) or type(exc).__name__}"))
        finally:
            cleanup_error = self._close_source()
            if self._stop.is_set():
                message = "Live reading stopped"
                if cleanup_error:
                    message += f"; cleanup failed: {cleanup_error}"
                self._publish(LiveUpdate("stopped", message))
            elif cleanup_error:
                self._publish(LiveUpdate("error", f"Source cleanup failed: {cleanup_error}"))

    def _publish_read(self, frame: CapturedFrame, read: Recognition, ranked: tuple[RankedWord, ...], started: float, solve_ms: float) -> None:
        elapsed_ms = (perf_counter() - started) * 1000
        if read.warnings:
            self._publish(LiveUpdate("review", "; ".join(read.warnings), frame, read, (), elapsed_ms, solve_ms))
        else:
            self._publish(LiveUpdate("ready", "Stable board ready; acceptance and scoring remain uncalibrated", frame, read, ranked, elapsed_ms, solve_ms))

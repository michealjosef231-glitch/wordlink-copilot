"""A real-time local recording source for exercising the live assistant."""

from __future__ import annotations

import math
from pathlib import Path
from time import perf_counter

import cv2

from wordlink.capture.sources import CapturedFrame, SourceUnavailable


class ReplaySource:
    """Read the current playback frame, skipping frames missed by the consumer.

    Opening and decoding happen on the consumer's worker. There is no playback
    thread or queued history. The original file is always opened read-only.
    """

    def __init__(self, path: Path | str, start: float = 0, loop: bool = False):
        if not math.isfinite(start) or start < 0:
            raise ValueError("Replay start must be a finite, nonnegative time")
        self.path = Path(path).expanduser()
        self.start = float(start)
        self.loop = loop
        self.label = f"Recording replay: {self.path.name}"
        self._capture: cv2.VideoCapture | None = None
        self._closed = False
        self._fps = 0.0
        self._count = 0
        self._anchor = 0.0
        self._index = -1

    def _open(self, now: float) -> None:
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            capture.release()
            raise SourceUnavailable(f"Cannot open recording: {self.path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps <= 0 or count <= 0:
            capture.release()
            raise SourceUnavailable("Recording has no usable frame rate or frames")
        first = int(self.start * fps)
        if first >= count:
            capture.release()
            raise SourceUnavailable("Replay start is beyond the end of the recording")
        if first and not capture.set(cv2.CAP_PROP_POS_FRAMES, first):
            capture.release()
            raise SourceUnavailable("Cannot seek to the requested replay start")
        self._capture = capture
        self._fps, self._count = fps, count
        self._index = first - 1
        self._anchor = now

    def read(self) -> CapturedFrame | None:
        if self._closed:
            raise SourceUnavailable("Recording replay is closed")
        now = perf_counter()
        if self._capture is None:
            self._open(now)
        capture = self._capture
        assert capture is not None
        first = int(self.start * self._fps)
        # Subtracting start from a large monotonic clock loses precision and
        # can target the preceding frame immediately after seeking.
        target = max(first, int((now - self._anchor + self.start) * self._fps))
        if target >= self._count:
            if not self.loop:
                return None
            # Restart at the requested start; do not decode previous loops.
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, first):
                raise SourceUnavailable("Cannot restart recording replay")
            self._index = first - 1
            self._anchor = now
            target = first
        while self._index < target:
            if not capture.grab():
                raise SourceUnavailable("Recording stopped decoding before its reported end")
            self._index += 1
        ok, image = capture.retrieve()
        if not ok or image is None or not image.size:
            raise SourceUnavailable("Cannot decode the current recording frame")
        return CapturedFrame(image=image, captured_at=now, media_time=self._index / self._fps)

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._closed = True

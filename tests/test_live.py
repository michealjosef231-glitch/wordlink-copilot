from __future__ import annotations

from dataclasses import FrozenInstanceError
from queue import Queue
from threading import Event, get_ident
from time import monotonic, sleep

import cv2
import numpy as np
import pytest

from wordlink.capture import live
from wordlink.capture.sources import CaptureError, CapturedFrame, CapturePermissionError, SourceUnavailable
from wordlink.model import Board, Recognition
from wordlink.solver.trie import Trie
from wordlink.vocabulary.policy import VocabularyPolicy

BOXES = tuple((17 + index % 4 * 40, 11 + index // 4 * 40, 32, 32) for index in range(16))
LETTERS = tuple("CATXXXXXXXXXXXXX")


def board_image(first_letter="C", first_dots=1):
    image = np.full((190, 210, 3), (140, 65, 20), dtype=np.uint8)
    letters = (first_letter, *LETTERS[1:])
    for index, (x, y, width, height) in enumerate(BOXES):
        image[y:y + height, x:x + width] = 255
        cv2.putText(image, letters[index], (x + 8, y + 21), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 1, cv2.LINE_8)
        for dot in range(first_dots if index == 0 else 1):
            cv2.circle(image, (x + 8 + dot * 5, y + 28), 1, (0, 0, 0), -1)
    return image


class FakeSource:
    label = "a fake selected window"

    def __init__(self):
        self.events = Queue()
        self.read_calls = 0
        self.close_calls = 0
        self.inside_read = False
        self.closed_during_read = False
        self.read_thread = None
        self.close_thread = None

    def read(self):
        self.read_calls += 1
        self.read_thread = get_ident()
        self.inside_read = True
        try:
            item = self.events.get(timeout=5)
            if isinstance(item, BaseException):
                raise item
            return item() if callable(item) else item
        finally:
            self.inside_read = False

    def push(self, image, age=0, media_time=None):
        self.events.put(lambda: CapturedFrame(image, monotonic() - age, media_time))

    def close(self):
        self.close_calls += 1
        self.close_thread = get_ident()
        self.closed_during_read |= self.inside_read


class Harness:
    def __init__(self, monkeypatch, *, config=None, recognition=None, detection=None):
        self.source = FakeSource()
        self.recognition_calls = 0
        self.detect_calls = 0
        self.solve_calls = 0
        self.assistant = live.LiveAssistant(self.source, Trie(["CAT", "DAT"]), VocabularyPolicy(), config or live.LiveConfig(sample_fps=60))

        def detect(image):
            self.detect_calls += 1
            if detection is not None:
                return detection(image)
            if not image.any():
                raise ValueError("No complete 4x4 grid")
            return BOXES

        def recognize(image):
            self.recognition_calls += 1
            if recognition is not None:
                return recognition(image)
            letter = "D" if np.array_equal(image[11:43, 17:49], board_image("D")[11:43, 17:49]) else "C"
            dots, _ = live.count_dots(image[11:43, 17:49])
            board = Board((letter, *LETTERS[1:]), (dots, *(1,) * 15), BOXES)
            return Recognition(board, (), 1.0)

        real_find = live.find_words

        def find_words(*args):
            self.solve_calls += 1
            return real_find(*args)

        monkeypatch.setattr(live, "detect_tiles", detect)
        monkeypatch.setattr(live, "recognize", recognize)
        monkeypatch.setattr(live, "find_words", find_words)
        self.assistant.start()

    def settle(self, image=None):
        image = board_image() if image is None else image
        for index in range(self.assistant.config.quiet_frames):
            before = self.detect_calls
            self.source.push(image, media_time=index)
            # Latest-only capture can drop a burst on a busy host. Feed each
            # intended quiet observation after the prior one was consumed.
            wait_until(lambda: self.detect_calls > before)
        return wait_update(self.assistant, "ready")

    def finish(self):
        self.assistant.stop(timeout=0)
        self.source.events.put(None)
        wait_until(lambda: not self.assistant.is_running)
        assert self.source.close_calls == 1
        assert not self.source.closed_during_read
        assert self.source.close_thread == self.source.read_thread


def wait_until(predicate, timeout=5):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(.002)
    raise AssertionError("Live worker did not reach its expected condition")


def wait_update(assistant, state, timeout=5):
    deadline = monotonic() + timeout
    observed = []
    while monotonic() < deadline:
        update = assistant.poll()
        if update is not None:
            observed.append(update.state)
            if update.state == state:
                return update
        sleep(.002)
    raise AssertionError(f"Expected {state}; observed {observed}")


def test_stable_board_emits_fresh_ready_heartbeats_without_repeating_ocr(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        ready = harness.settle()
        assert ready.recognition is not None
        assert [candidate.found.word for candidate in ready.ranked_words] == ["CAT"]
        assert harness.recognition_calls == harness.solve_calls == 1
        sleep(.01)
        harness.source.push(board_image(), media_time=9)
        heartbeat = wait_update(harness.assistant, "ready")
        assert heartbeat.sequence > ready.sequence
        assert heartbeat.frame.captured_at > ready.frame.captured_at
        assert heartbeat.frame.media_time == 9
        assert heartbeat.ranked_words == ready.ranked_words
        assert harness.recognition_calls == harness.solve_calls == 1
        assert heartbeat.solve_ms == 0
    finally:
        harness.finish()


def test_letter_movement_clears_words_before_the_new_board_settles(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        harness.settle()
        changed = board_image("D")
        harness.source.push(changed)
        moving = wait_update(harness.assistant, "waiting")
        assert not moving.ranked_words
        assert moving.recognition is None
        harness.source.push(changed)
        harness.source.push(changed)
        ready = wait_update(harness.assistant, "ready")
        assert ready.recognition.board.letters[0] == "D"
        assert [candidate.found.word for candidate in ready.ranked_words] == ["DAT"]
        assert harness.recognition_calls == 3  # Verify changed glyph, then read settled board.
        assert harness.solve_calls == 2
    finally:
        harness.finish()


def test_dot_only_change_below_motion_threshold_invalidates_identity_and_ranking(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        first = harness.settle()
        changed = board_image(first_dots=2)
        old_crop = live._board_crop(board_image(), BOXES)
        new_crop = live._board_crop(changed, BOXES)
        assert np.abs(old_crop.astype(float) - new_crop).mean() / 255 < harness.assistant.config.threshold
        harness.source.push(changed)
        assert not wait_update(harness.assistant, "waiting").ranked_words
        harness.source.push(changed)
        harness.source.push(changed)
        second = wait_update(harness.assistant, "ready")
        assert second.recognition.board.letters == first.recognition.board.letters
        assert second.recognition.board.dots[0] == 2
        assert second.ranked_words[0].found.dot_sum == first.ranked_words[0].found.dot_sum + 1
        assert harness.recognition_calls == harness.solve_calls == 2
    finally:
        harness.finish()


def test_motion_outside_exact_detected_grid_does_not_invalidate_board(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        harness.settle()
        image = board_image()
        image[:8] = 255
        image[:, 190:] = 0
        harness.source.push(image)
        update = wait_update(harness.assistant, "ready")
        assert update.ranked_words
        assert harness.recognition_calls == 1
    finally:
        harness.finish()


def test_disappearing_grid_clears_suggestions_and_requires_settling_again(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        harness.settle()
        harness.source.push(np.zeros_like(board_image()))
        missing = wait_update(harness.assistant, "waiting")
        assert "complete board" in missing.message
        assert not missing.ranked_words
        harness.source.push(board_image())
        assert not wait_update(harness.assistant, "waiting").ranked_words
        harness.source.push(board_image())
        harness.source.push(board_image())
        assert wait_update(harness.assistant, "ready").ranked_words
        assert harness.recognition_calls == 2
    finally:
        harness.finish()


def test_uncertain_recognition_holds_review_and_never_runs_solver(monkeypatch):
    board = Board(LETTERS, (1,) * 16, BOXES)
    harness = Harness(monkeypatch, recognition=lambda _: Recognition(board, (), 1, ("Tile 1: uncertain letter",)))
    try:
        for _ in range(3):
            harness.source.push(board_image())
        review = wait_update(harness.assistant, "review")
        assert review.recognition.warnings
        assert not review.ranked_words
        harness.source.push(board_image(), media_time=4)
        repeated = wait_update(harness.assistant, "review")
        assert repeated.frame.media_time == 4
        assert harness.recognition_calls == 1
        assert harness.solve_calls == 0
    finally:
        harness.finish()


def test_stale_capture_is_rejected_before_ocr(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        harness.source.push(board_image(), age=3)
        update = wait_update(harness.assistant, "waiting")
        # Ignore the initial waiting event if the worker has not consumed yet.
        if "stale" not in update.message:
            update = wait_update(harness.assistant, "waiting")
        assert "stale" in update.message
        assert update.frame is None
        assert not update.ranked_words
        assert harness.recognition_calls == 0
    finally:
        harness.finish()


def test_poll_expires_consumed_ready_if_backend_stalls_then_fresh_heartbeat_recovers(monkeypatch):
    harness = Harness(monkeypatch, config=live.LiveConfig(sample_fps=60, max_frame_age=.08))
    try:
        harness.settle()
        sleep(.10)
        expired = wait_update(harness.assistant, "waiting")
        assert "stale" in expired.message
        assert not expired.ranked_words
        assert harness.assistant.poll() is None
        harness.source.push(board_image())
        assert wait_update(harness.assistant, "ready").ranked_words
        assert harness.recognition_calls == 1
    finally:
        harness.finish()


@pytest.mark.parametrize("error,state", [
    (CapturePermissionError("consent missing"), "permission"),
    (PermissionError("access denied"), "permission"),
    (SourceUnavailable("window closed"), "disconnected"),
    (CaptureError("backend failed"), "error"),
    (RuntimeError("unexpected backend failure"), "error"),
])
def test_backend_failures_clear_words_and_close_on_worker(monkeypatch, error, state):
    harness = Harness(monkeypatch)
    harness.settle()
    harness.source.events.put(error)
    update = wait_update(harness.assistant, state)
    wait_until(lambda: not harness.assistant.is_running)
    assert not update.ranked_words
    assert update.recognition is None
    assert str(error) in update.message
    assert harness.source.close_calls == 1
    assert harness.source.close_thread == harness.source.read_thread
    harness.assistant.stop()
    assert harness.source.close_calls == 1


def test_recording_end_clears_words_and_prevents_restart(monkeypatch):
    harness = Harness(monkeypatch)
    harness.settle()
    harness.source.events.put(None)
    update = wait_update(harness.assistant, "ended")
    wait_until(lambda: not harness.assistant.is_running)
    assert not update.ranked_words
    assert harness.source.close_calls == 1
    with pytest.raises(RuntimeError, match="fresh source"):
        harness.assistant.start()


def test_start_is_idempotent_and_stop_before_start_closes_once(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        worker = harness.assistant._thread
        harness.assistant.start()
        assert harness.assistant._thread is worker
    finally:
        harness.finish()
    source = FakeSource()
    assistant = live.LiveAssistant(source, Trie([]), VocabularyPolicy())
    assistant.stop()
    assistant.stop()
    assert source.close_calls == 1
    assert source.close_thread == get_ident()
    assert source.read_calls == 0
    assert not assistant.is_running
    assert assistant.poll().state == "stopped"
    with pytest.raises(RuntimeError, match="fresh source"):
        assistant.start()


def test_stop_during_read_is_bounded_closes_after_read_and_never_publishes_late_ready(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        harness.settle()
        wait_until(lambda: harness.source.inside_read)
        started = monotonic()
        harness.assistant.stop(timeout=.01)
        assert monotonic() - started < .2
        assert wait_update(harness.assistant, "stopped").ranked_words == ()
        assert harness.source.close_calls == 0
        harness.source.push(board_image())
        wait_until(lambda: not harness.assistant.is_running)
        assert harness.source.close_calls == 1
        assert not harness.source.closed_during_read
        assert harness.assistant.poll().state == "stopped"
        assert harness.assistant.poll() is None
    finally:
        if harness.assistant.is_running:
            harness.finish()


def test_cancellation_during_ocr_discards_result_and_solver_work(monkeypatch):
    entered, release = Event(), Event()
    board = Board(LETTERS, (1,) * 16, BOXES)

    def recognize(_):
        entered.set()
        assert release.wait(2)
        return Recognition(board, (), 1)

    harness = Harness(monkeypatch, recognition=recognize)
    try:
        for _ in range(3):
            harness.source.push(board_image())
        assert entered.wait(2)
        harness.assistant.stop(timeout=.01)
        assert wait_update(harness.assistant, "stopped").ranked_words == ()
        assert not harness.source.closed_during_read
        release.set()
        harness.source.events.put(None)  # Release the independent capture worker.
        wait_until(lambda: not harness.assistant.is_running)
        assert harness.solve_calls == 0
        assert harness.assistant._last_update.state == "stopped"
        assert harness.source.close_calls == 1
    finally:
        release.set()
        if harness.assistant.is_running:
            harness.finish()


def test_latest_queue_has_no_backlog(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        harness.settle()
        for marker in range(10, 16):
            harness.source.push(board_image(), media_time=marker)
        wait_until(lambda: harness.source.read_calls >= 10)
        latest = harness.assistant.poll()
        assert latest.state == "ready"
        assert latest.frame.media_time == 15
        assert harness.assistant.poll() is None
        assert harness.recognition_calls == 1
    finally:
        harness.finish()


def test_processing_resize_preserves_capture_time_and_matches_published_boxes(monkeypatch):
    original = np.full((2000, 2500, 3), 255, dtype=np.uint8)
    captured_at = monotonic()
    source = FakeSource()
    source.events.put(CapturedFrame(original, captured_at, 9))
    source.events.put(lambda: CapturedFrame(original, monotonic(), 10))
    monkeypatch.setattr(live, "detect_tiles", lambda _: BOXES)
    monkeypatch.setattr(live, "_content_fingerprint", lambda *_: b"unchanged")
    board = Board(LETTERS, (1,) * 16, BOXES)
    monkeypatch.setattr(live, "recognize", lambda _: Recognition(board, (), 1))
    assistant = live.LiveAssistant(source, Trie(["CAT"]), VocabularyPolicy(), live.LiveConfig(sample_fps=60, quiet_frames=2))
    assistant.start()
    try:
        update = wait_update(assistant, "ready")
        assert update.frame.image.shape == (819, 1024, 3)
        assert update.frame.captured_at > captured_at
        assert update.frame.image is not original
        assert not update.frame.image.flags.writeable
        assert max(box[0] + box[2] for box in update.recognition.board.boxes) < update.frame.image.shape[1]
    finally:
        assistant.stop(timeout=0)
        source.events.put(None)
        wait_until(lambda: not assistant.is_running)


@pytest.mark.parametrize("kwargs", [{"preview_fps": 0}, {"preview_fps": 61}, {"sample_fps": 0}, {"sample_fps": 61}, {"quiet_frames": 1}, {"threshold": 0}, {"threshold": float("nan")}, {"max_frame_age": -1}])
def test_invalid_live_config_fails_clearly(kwargs):
    with pytest.raises(ValueError):
        live.LiveConfig(**kwargs)


def test_updates_and_config_are_frozen():
    with pytest.raises(FrozenInstanceError):
        live.LiveConfig().sample_fps = 5
    with pytest.raises(FrozenInstanceError):
        live.LiveUpdate("waiting", "pending").state = "ready"


def test_content_signature_tolerates_codec_noise_but_catches_ink_and_dot_changes():
    glyphs = tuple(np.zeros((64, 64), dtype=np.uint8) for _ in range(16))
    baseline = live._ContentSignature(BOXES, glyphs, (1,) * 16, (False,) * 16)
    noisy_glyphs = list(glyphs)
    noisy_glyphs[0] = glyphs[0].copy()
    noisy_glyphs[0].flat[:40] = 255  # Less than 1% changed normalized pixels.
    shifted_boxes = tuple((x + 1, y, width, height) for x, y, width, height in BOXES)
    noisy = live._ContentSignature(shifted_boxes, tuple(noisy_glyphs), (1,) * 16, (False,) * 16)
    assert live._same_content(baseline, noisy)

    changed_glyphs = list(glyphs)
    changed_glyphs[0] = glyphs[0].copy()
    changed_glyphs[0].flat[:100] = 255  # More than 2% of one tile changed.
    changed = live._ContentSignature(BOXES, tuple(changed_glyphs), (1,) * 16, (False,) * 16)
    assert not live._same_content(baseline, changed)
    assert not live._same_content(baseline, live._ContentSignature(BOXES, glyphs, (2,) + (1,) * 15, (False,) * 16))
    assert not live._same_content(baseline, live._ContentSignature(BOXES, glyphs, (1,) * 16, (True,) + (False,) * 15))
    resized_boxes = tuple((x + 4, y, width, height) for x, y, width, height in BOXES)
    assert not live._same_content(baseline, live._ContentSignature(resized_boxes, glyphs, (1,) * 16, (False,) * 16))


def test_gradual_board_translation_refreshes_cached_path_coordinates(monkeypatch):
    def boxes_for(image):
        shift = int(image[0, 0, 0])
        return tuple((x + shift, y, width, height) for x, y, width, height in BOXES)

    def recognition(image):
        return Recognition(Board(LETTERS, (1,) * 16, boxes_for(image)), (), 1.0)

    harness = Harness(monkeypatch, recognition=recognition, detection=boxes_for)

    def translated(shift):
        image = np.full((190, 240, 3), (140, 65, 20), dtype=np.uint8)
        image[:, shift:shift + 210] = board_image()
        image[0, 0, 0] = shift  # Geometry marker outside the actual tile crop.
        return image

    try:
        baseline = harness.settle(translated(0))
        previous = live._content_fingerprint(baseline.frame.image, BOXES)
        for shift in range(3, 25, 3):
            image = translated(shift)
            current = live._content_fingerprint(image, boxes_for(image))
            assert live._same_content(previous, current)  # Adjacent frames look equivalent.
            previous = current
            harness.source.push(image, media_time=shift)
            observed = []

            def got_frame():
                update = harness.assistant.poll()
                if update and update.frame and update.frame.media_time == shift:
                    observed.append(update)
                    return update.state in ("ready", "waiting")
                return False

            wait_until(got_frame)
            update = observed[-1]
            if update.state == "ready":
                cached_x = update.recognition.board.boxes[0][0]
                assert abs(cached_x - (BOXES[0][0] + shift)) <= 3
            else:
                assert not update.ranked_words
        assert harness.recognition_calls >= 3
        assert harness.solve_calls == 1  # Geometry updates do not change legal words.
    finally:
        harness.finish()


def test_gradual_glyph_changes_are_compared_with_the_recognized_frame(monkeypatch):
    def signature(image, boxes):
        glyphs = [np.zeros((64, 64), dtype=np.uint8) for _ in range(16)]
        glyphs[0].flat[:int(image[0, 0, 0])] = 255
        return live._ContentSignature(boxes, tuple(glyphs), (1,) * 16, (False,) * 16)

    harness = Harness(monkeypatch)
    monkeypatch.setattr(live, "_content_fingerprint", signature)
    try:
        baseline = board_image()
        baseline[0, 0, 0] = 0
        harness.settle(baseline)
        for amount in (20, 40, 60, 80, 100):
            image = baseline.copy()
            image[0, 0, 0] = amount
            harness.source.push(image, media_time=amount)
            wait_update(harness.assistant, "ready")
        # Each step is under 1%, but total glyph drift exceeds the 2% tolerance.
        assert harness.recognition_calls == 2
    finally:
        harness.finish()


def test_selected_tile_glyph_variation_rechecks_same_board_without_losing_ready(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        baseline = board_image()
        harness.settle(baseline)
        highlighted = baseline.copy()
        x, y, _, _ = BOXES[0]
        cv2.rectangle(highlighted, (x + 4, y + 9), (x + 20, y + 15), (0, 0, 0), -1)
        original = live._content_fingerprint(baseline, BOXES)
        changed = live._content_fingerprint(highlighted, BOXES)
        assert not live._same_content(original, changed)

        published = []
        original_publish = harness.assistant._publish

        def observe(update):
            published.append(update)
            original_publish(update)

        monkeypatch.setattr(harness.assistant, "_publish", observe)
        for image in (highlighted, baseline, highlighted):
            published.clear()
            harness.source.push(image)
            ready = wait_update(harness.assistant, "ready")
            assert ready.recognition.board.letters == LETTERS
            assert [candidate.found.word for candidate in ready.ranked_words] == ["CAT"]
            # Observe every publication, since the latest-only queue can hide
            # a provisional reading event that briefly empties the GUI.
            assert [update.state for update in published] == ["ready"]
        assert harness.recognition_calls >= 2
        assert harness.solve_calls == 1
    finally:
        harness.finish()


def test_slow_same_board_verification_expires_old_ready_without_refreshing_it(monkeypatch):
    entered, release = Event(), Event()
    checking = [False]
    board = Board(LETTERS, (1,) * 16, BOXES)

    def recognition(image):
        if checking[0]:
            entered.set()
            assert release.wait(2), "Verification was not released"
        return Recognition(board, (), 1.0)

    harness = Harness(monkeypatch, config=live.LiveConfig(sample_fps=60, max_frame_age=.15),
                      recognition=recognition)
    try:
        baseline = board_image()
        ready = harness.settle(baseline)
        highlighted = baseline.copy()
        x, y, _, _ = BOXES[0]
        cv2.rectangle(highlighted, (x + 4, y + 9), (x + 20, y + 15), (0, 0, 0), -1)
        clock = [ready.frame.captured_at + .01]
        monkeypatch.setattr(live, "monotonic", lambda: clock[0])
        checking[0] = True
        harness.source.events.put(CapturedFrame(highlighted, clock[0]))
        wait_until(entered.is_set)
        # Equivalent ink is being checked; no empty provisional update and
        # no heartbeat manufactured from the unverified incoming image.
        assert harness.assistant.poll() is None
        assert harness.assistant._last_update.frame.captured_at == ready.frame.captured_at
        clock[0] += .18
        expired = wait_update(harness.assistant, "waiting")
        assert "stale" in expired.message
        assert not expired.ranked_words
        release.set()
        stale_read = wait_update(harness.assistant, "waiting")
        assert "stale while reading" in stale_read.message
        assert not stale_read.ranked_words
        checking[0] = False
        monkeypatch.setattr(live, "monotonic", monotonic)
        assert harness.settle(baseline).ranked_words
    finally:
        release.set()
        harness.finish()


@pytest.mark.parametrize("outcome", ["changed", "warning", "invalid"])
def test_quiet_ink_verification_clears_ready_when_new_read_cannot_be_reused(monkeypatch, outcome):
    checking = [False]
    original = Recognition(Board(LETTERS, (1,) * 16, BOXES), (), 1.0)

    def recognition(image):
        if not checking[0]:
            return original
        if outcome == "invalid":
            raise ValueError("Uncertain tile content")
        if outcome == "warning":
            return Recognition(original.board, (), 1.0, ("Tile 1: uncertain letter",))
        return Recognition(Board(("D", *LETTERS[1:]), (1,) * 16, BOXES), (), 1.0)

    harness = Harness(monkeypatch, recognition=recognition)
    try:
        baseline = board_image()
        harness.settle(baseline)
        highlighted = baseline.copy()
        x, y, _, _ = BOXES[0]
        cv2.rectangle(highlighted, (x + 4, y + 9), (x + 20, y + 15), (0, 0, 0), -1)
        checking[0] = True
        harness.source.push(highlighted)
        update = wait_update(harness.assistant, "waiting" if outcome == "changed" else "review")
        assert not update.ranked_words
        if outcome == "changed":
            assert "Board changed" in update.message
            assert update.recognition is None
        else:
            assert "uncertain" in update.message.casefold()
        assert harness.recognition_calls == 2
    finally:
        harness.finish()


def test_preview_continues_during_blocked_ocr_and_only_latest_frame_is_retained(monkeypatch):
    entered, release = Event(), Event()
    board = Board(LETTERS, (1,) * 16, BOXES)

    def recognition(_):
        entered.set()
        assert release.wait(3)
        return Recognition(board, (), 1)

    harness = Harness(monkeypatch, recognition=recognition)
    try:
        for _ in range(3):
            harness.source.push(board_image())
        assert entered.wait(2)
        previous = harness.assistant.poll_frame()
        assert previous is not None
        assert harness.assistant.poll_frame() is None
        for marker in range(6):
            harness.source.push(board_image(), media_time=marker)
        wait_until(lambda: harness.source.read_calls >= 10)
        newest = harness.assistant.poll_frame()
        assert newest.media_time == 5
        assert newest.captured_at > previous.captured_at
        assert not newest.image.flags.writeable
        assert harness.assistant.poll_frame() is None
        assert harness.recognition_calls == 1
        release.set()
        assert wait_update(harness.assistant, "ready").ranked_words
    finally:
        release.set()
        harness.finish()


@pytest.mark.parametrize("event,state", [(None, "ended"),
    (SourceUnavailable("disconnected during OCR"), "disconnected"),
    (CapturePermissionError("permission revoked during OCR"), "permission")])
def test_source_terminal_during_ocr_has_priority_and_discards_pending_preview(monkeypatch, event, state):
    entered, release = Event(), Event()
    board = Board(LETTERS, (1,) * 16, BOXES)

    def recognition(_):
        entered.set()
        assert release.wait(3)
        return Recognition(board, (), 1)

    harness = Harness(monkeypatch, recognition=recognition)
    try:
        for _ in range(3):
            harness.source.push(board_image())
        assert entered.wait(2)
        harness.source.events.put(event)
        assert not wait_update(harness.assistant, state).ranked_words
        assert harness.assistant.poll_frame() is None
        release.set()
        wait_until(lambda: not harness.assistant.is_running)
        assert harness.assistant.poll() is None
        assert harness.solve_calls == 0
        assert harness.source.close_calls == 1
        assert harness.source.close_thread == harness.source.read_thread
    finally:
        release.set()
        harness.finish()


def test_duplicate_capture_timestamps_never_count_as_multiple_quiet_frames(monkeypatch):
    harness = Harness(monkeypatch)
    try:
        stamp = monotonic()
        frame = CapturedFrame(board_image(), stamp)
        for _ in range(5):
            harness.source.events.put(frame)
        wait_until(lambda: harness.source.read_calls >= 6)
        assert harness.recognition_calls == 0
        preview = harness.assistant.poll_frame()
        assert preview.captured_at == stamp
        assert harness.assistant.poll_frame() is None
        harness.source.push(board_image())
        harness.source.push(board_image())
        assert wait_update(harness.assistant, "ready").ranked_words
    finally:
        harness.finish()


def test_stale_source_frame_invalidates_preview_and_inflight_ocr(monkeypatch):
    entered, release = Event(), Event()
    board = Board(LETTERS, (1,) * 16, BOXES)

    def recognition(_):
        entered.set()
        assert release.wait(3)
        return Recognition(board, (), 1)

    harness = Harness(monkeypatch, recognition=recognition)
    try:
        for _ in range(3):
            harness.source.push(board_image())
        assert entered.wait(2)
        harness.source.push(board_image(), age=3)
        assert "stale" in wait_update(harness.assistant, "waiting").message
        assert harness.assistant.poll_frame() is None
        release.set()
        assert "stale while reading" in wait_update(harness.assistant, "waiting").message
        assert harness.solve_calls == 0
        assert harness.settle().ranked_words
    finally:
        release.set()
        harness.finish()

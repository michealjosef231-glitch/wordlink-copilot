import cv2
import numpy as np
import pytest

import wordlink.capture.replay as replay
from wordlink.capture.sources import SourceUnavailable


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / "replay.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 64))
    assert writer.isOpened()
    for index in range(20):
        writer.write(np.full((64, 64, 3), index * 10, dtype=np.uint8))
    writer.release()
    return path


def test_replay_uses_playback_time_and_skips_missed_frames(recording, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(replay, "perf_counter", lambda: now[0])
    source = replay.ReplaySource(recording, start=.5)
    try:
        first = source.read()
        assert first.media_time == pytest.approx(.5)
        assert first.image.mean() == pytest.approx(50, abs=3)
        now[0] += .9
        latest = source.read()
        assert latest.media_time == pytest.approx(1.4)
        assert latest.image.mean() == pytest.approx(140, abs=3)
        assert latest.captured_at == now[0]
        now[0] += 1
        assert source.read() is None
    finally:
        source.close()


def test_replay_loop_restarts_at_requested_position(recording, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(replay, "perf_counter", lambda: now[0])
    source = replay.ReplaySource(recording, start=.5, loop=True)
    try:
        assert source.read().media_time == pytest.approx(.5)
        now[0] += 10
        assert source.read().media_time == pytest.approx(.5)
    finally:
        source.close()


def test_replay_close_and_invalid_sources(recording, tmp_path):
    with pytest.raises(ValueError, match="finite"):
        replay.ReplaySource(recording, start=float("nan"))
    source = replay.ReplaySource(recording)
    source.close()
    source.close()
    with pytest.raises(SourceUnavailable, match="closed"):
        source.read()
    missing = replay.ReplaySource(tmp_path / "missing.mp4")
    with pytest.raises(SourceUnavailable, match="Cannot open"):
        missing.read()
    outside = replay.ReplaySource(recording, start=5)
    with pytest.raises(SourceUnavailable, match="beyond"):
        outside.read()

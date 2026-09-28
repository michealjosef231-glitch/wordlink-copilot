import numpy as np
import pytest

from wordlink.capture.video import SettleDetector, iter_frames, read_frame


def test_settle_detector_waits_then_emits_only_once_and_recovers():
    detector = SettleDetector(quiet_frames=3)
    first = np.full((50, 50, 3), 30, dtype=np.uint8)
    falling = first.copy()
    falling[:25] = 180
    assert not detector.update(first)
    assert not detector.update(falling)
    assert not detector.update(first)
    assert not detector.update(first)
    assert detector.update(first)
    assert not detector.update(first)
    second = np.full_like(first, 200)
    assert not detector.update(second)
    assert not detector.update(second)
    assert detector.update(second)


def test_invalid_capture_inputs_fail_clearly(tmp_path):
    with pytest.raises(ValueError, match="negative"):
        read_frame(tmp_path / "missing.mp4", -1)
    with pytest.raises(ValueError, match="Sampling"):
        list(iter_frames(tmp_path / "missing.mp4", sample_fps=0))
    with pytest.raises(ValueError, match="Cannot open"):
        read_frame(tmp_path / "missing.mp4", 0)


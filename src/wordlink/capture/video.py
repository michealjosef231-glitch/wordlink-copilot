from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    frame_count: int
    width: int
    height: int

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps if self.fps else 0.0


def video_info(path: Path) -> VideoInfo:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open recording: {path}")
        return VideoInfo(
            capture.get(cv2.CAP_PROP_FPS), int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
    finally:
        capture.release()


def read_frame(path: Path, seconds: float) -> np.ndarray:
    if seconds < 0:
        raise ValueError("Frame time cannot be negative")
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open recording: {path}")
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok:
            raise ValueError(f"No frame at {seconds:.3f}s in {path}")
        return frame
    finally:
        capture.release()


def iter_frames(path: Path, sample_fps: float = 4.0, start: float = 0.0,
                stop: float | None = None) -> Iterator[tuple[float, np.ndarray]]:
    if not 0 < sample_fps <= 60:
        raise ValueError("Sampling rate must be between 0 and 60 fps")
    if start < 0 or (stop is not None and stop <= start):
        raise ValueError("Invalid recording interval")
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open recording: {path}")
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0:
            raise ValueError("Recording has no usable frame rate")
        duration = count / fps
        end = min(stop, duration) if stop is not None else duration
        sample = 0
        while (timestamp := start + sample / sample_fps) < end:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                break
            yield timestamp, frame
            sample += 1
    finally:
        capture.release()


class SettleDetector:
    """Wait for consecutive quiet frames; emit once until the board moves again."""

    def __init__(self, quiet_frames: int = 3, threshold: float = 0.008):
        if quiet_frames < 2 or threshold <= 0:
            raise ValueError("Need at least two quiet frames and a positive threshold")
        self.quiet_frames = quiet_frames
        self.threshold = threshold
        self.previous: np.ndarray | None = None
        self.quiet_count = 0
        self.emitted = False

    def update(self, board_crop: np.ndarray) -> bool:
        if board_crop.size == 0:
            raise ValueError("Empty board crop")
        gray = cv2.cvtColor(board_crop, cv2.COLOR_BGR2GRAY) if board_crop.ndim == 3 else board_crop
        current = cv2.resize(gray, (160, 160), interpolation=cv2.INTER_AREA).astype(np.float32)
        quiet = self.previous is not None and float(np.abs(current - self.previous).mean()) / 255 < self.threshold
        self.previous = current
        if quiet:
            self.quiet_count += 1
        else:
            self.quiet_count = 1
            self.emitted = False
        if self.quiet_count >= self.quiet_frames and not self.emitted:
            self.emitted = True
            return True
        return False


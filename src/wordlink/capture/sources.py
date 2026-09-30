"""Shared, local-only frame source contract for live reading and replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class CaptureError(RuntimeError):
    """A selected image source cannot safely supply a frame."""


class CapturePermissionError(CaptureError):
    """macOS requires Screen Recording consent for the selected window."""


class SourceUnavailable(CaptureError):
    """The selected window or recording is unavailable."""


@dataclass(frozen=True)
class CapturedFrame:
    image: np.ndarray
    captured_at: float
    media_time: float | None = None


class FrameSource(Protocol):
    label: str

    def read(self) -> CapturedFrame | None:
        """Return a fresh BGR frame, or None when a replay has ended."""
        ...

    def close(self) -> None:
        """Release the source. This method must be safe to call again."""
        ...

"""Monterey-compatible capture of one selected window, using system frameworks.

Frameworks load lazily, so importing this module is portable. No function reads
the desktop: image capture uses only kCGWindowListOptionIncludingWindow and a
positive selected window ID. Screen Recording requests are explicit API calls.
"""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
from functools import lru_cache
import math
import os
import plistlib
import subprocess
import sys
import threading
import time

import numpy as np

from wordlink.capture.sources import (
    CapturedFrame, CaptureError, CapturePermissionError, SourceUnavailable,
)


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    app: str
    title: str
    pid: int
    bounds: tuple[int, int, int, int]


class _CGPoint(ct.Structure):
    _fields_ = [("x", ct.c_double), ("y", ct.c_double)]


class _CGSize(ct.Structure):
    _fields_ = [("width", ct.c_double), ("height", ct.c_double)]


class _CGRect(ct.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


_ONSCREEN_USER_WINDOWS = (1 << 0) | (1 << 4)
_INCLUDING_SELECTED_WINDOW = 1 << 3
_WINDOW_IMAGE_OPTIONS = (1 << 0) | (1 << 4)  # no shadow; nominal pixel size
_BGRA_BITMAP_INFO = (2 << 12) | 2  # little-endian, premultiplied alpha first
_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def _bind(library, name: str, arguments: list, result):
    function = getattr(library, name)
    function.argtypes = arguments
    function.restype = result
    return function


class _Quartz:
    """Small ctypes boundary with balanced Create/Copy and Release operations."""

    def __init__(self) -> None:
        pointer = ct.c_void_p
        try:
            self.cg = ct.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            self.cf = ct.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            _bind(self.cg, "CGWindowListCopyWindowInfo", [ct.c_uint32, ct.c_uint32], pointer)
            _bind(self.cg, "CGPreflightScreenCaptureAccess", [], ct.c_bool)
            _bind(self.cg, "CGRequestScreenCaptureAccess", [], ct.c_bool)
            _bind(self.cg, "CGWindowListCreateImage", [_CGRect, ct.c_uint32, ct.c_uint32, ct.c_uint32], pointer)
            _bind(self.cg, "CGImageGetWidth", [pointer], ct.c_size_t)
            _bind(self.cg, "CGImageGetHeight", [pointer], ct.c_size_t)
            _bind(self.cg, "CGImageRelease", [pointer], None)
            _bind(self.cg, "CGColorSpaceCreateDeviceRGB", [], pointer)
            _bind(self.cg, "CGColorSpaceRelease", [pointer], None)
            _bind(self.cg, "CGBitmapContextCreate", [pointer, ct.c_size_t, ct.c_size_t,
                                                     ct.c_size_t, ct.c_size_t, pointer, ct.c_uint32], pointer)
            _bind(self.cg, "CGContextDrawImage", [pointer, _CGRect, pointer], None)
            _bind(self.cg, "CGContextRelease", [pointer], None)
            _bind(self.cf, "CFRelease", [pointer], None)
            _bind(self.cf, "CFPropertyListCreateData", [pointer, pointer, ct.c_long,
                                                       ct.c_ulong, ct.POINTER(pointer)], pointer)
            _bind(self.cf, "CFDataGetLength", [pointer], ct.c_long)
            _bind(self.cf, "CFDataGetBytePtr", [pointer], pointer)
            self.null_rect = _CGRect.in_dll(self.cg, "CGRectNull")
        except (OSError, AttributeError, ValueError) as error:
            raise SourceUnavailable("The macOS window-capture APIs are unavailable") from error

    def screen_allowed(self) -> bool:
        return bool(self.cg.CGPreflightScreenCaptureAccess())

    def request_screen_access(self) -> bool:
        return bool(self.cg.CGRequestScreenCaptureAccess())

    def window_records(self) -> list[dict]:
        array = self.cg.CGWindowListCopyWindowInfo(_ONSCREEN_USER_WINDOWS, 0)
        if not array:
            raise SourceUnavailable("No macOS graphical window session is available")
        data = None
        error = ct.c_void_p()
        try:
            # Window metadata is a property list; native serialization avoids
            # unsafe CF dictionary/string casts and borrowed-pointer lifetimes.
            data = self.cf.CFPropertyListCreateData(None, array, 200, 0, ct.byref(error))
            if not data:
                raise CaptureError("Could not decode macOS window metadata")
            length = self.cf.CFDataGetLength(data)
            pointer = self.cf.CFDataGetBytePtr(data)
            if length <= 0 or not pointer:
                raise CaptureError("macOS returned empty window metadata")
            records = plistlib.loads(ct.string_at(pointer, length))
            if not isinstance(records, list):
                raise CaptureError("macOS returned invalid window metadata")
            return records
        except (plistlib.InvalidFileException, ValueError, OverflowError) as exc:
            raise CaptureError("Could not decode macOS window metadata") from exc
        finally:
            if error.value:
                self.cf.CFRelease(error)
            if data:
                self.cf.CFRelease(data)
            self.cf.CFRelease(array)

    def capture_window(self, window_id: int) -> np.ndarray:
        image = self.cg.CGWindowListCreateImage(
            self.null_rect, _INCLUDING_SELECTED_WINDOW, window_id, _WINDOW_IMAGE_OPTIONS,
        )
        if not image:
            raise SourceUnavailable("The selected window no longer supplies an image")
        space = context = None
        try:
            width = int(self.cg.CGImageGetWidth(image))
            height = int(self.cg.CGImageGetHeight(image))
            if width < 2 or height < 2:
                raise SourceUnavailable("The selected window has no readable pixels")
            if width * height > 64_000_000:
                raise CaptureError("The selected window image is too large")
            row_stride = (width * 4 + 15) // 16 * 16
            storage = np.zeros((height, row_stride), dtype=np.uint8)
            pixels = np.ndarray((height, width, 4), dtype=np.uint8,
                                buffer=storage, strides=(row_stride, 4, 1))
            space = self.cg.CGColorSpaceCreateDeviceRGB()
            if not space:
                raise CaptureError("Could not create the RGB capture color space")
            context = self.cg.CGBitmapContextCreate(
                storage.ctypes.data, width, height, 8, row_stride, space, _BGRA_BITMAP_INFO,
            )
            if not context:
                raise CaptureError("Could not create the window capture bitmap")
            self.cg.CGContextDrawImage(
                context, _CGRect(_CGPoint(0, 0), _CGSize(width, height)), image,
            )
            if not pixels[:, :, 3].any():
                raise SourceUnavailable("The selected window pixels are unavailable or protected")
            # Known BGRA context, explicit padded stride. Premultiplied color
            # composites transparent corners onto black without any desktop.
            return pixels[:, :, :3].copy()
        finally:
            if context:
                self.cg.CGContextRelease(context)
            if space:
                self.cg.CGColorSpaceRelease(space)
            self.cg.CGImageRelease(image)


@lru_cache(maxsize=1)
def _get_native() -> _Quartz:
    if sys.platform != "darwin":
        raise SourceUnavailable("Native window capture is available only on macOS")
    return _Quartz()


def _normal_windows(records: list[dict]) -> list[WindowInfo]:
    windows = []
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            if (record.get("kCGWindowLayer") != 0 or not record.get("kCGWindowIsOnscreen", False)
                    or float(record.get("kCGWindowAlpha", 1.0)) <= 0):
                continue
            window_id = int(record["kCGWindowNumber"])
            pid = int(record["kCGWindowOwnerPID"])
            raw_bounds = record["kCGWindowBounds"]
            values = tuple(float(raw_bounds[key]) for key in ("X", "Y", "Width", "Height"))
            if not all(math.isfinite(value) for value in values):
                continue
            bounds = tuple(round(value) for value in values)
            if not (0 < window_id <= 0xFFFFFFFF and pid > 0 and bounds[2] > 0 and bounds[3] > 0):
                continue
            app = str(record.get("kCGWindowOwnerName") or f"Process {pid}")
            title = str(record.get("kCGWindowName") or "")
            windows.append(WindowInfo(window_id, app, title, pid, bounds))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return sorted(windows, key=lambda window: (
        not window.app.casefold().startswith("quicktime"), window.app.casefold(),
        window.title.casefold(), window.window_id,
    ))


def list_windows() -> list[WindowInfo]:
    """List visible normal user windows, preferring QuickTime mirror windows.

    Missing titles are retained and are never used as evidence of permission.
    Bounds are screen-point (x, y, width, height) values, not capture pixel size.
    """
    if sys.platform != "darwin":
        return []
    return _normal_windows(_get_native().window_records())


def screen_recording_allowed() -> bool:
    """Query explicit CoreGraphics consent without prompting or reading pixels."""
    return sys.platform == "darwin" and _get_native().screen_allowed()


def request_screen_recording() -> bool:
    """Explicitly request macOS consent; call from the user's permission button."""
    return sys.platform == "darwin" and _get_native().request_screen_access()


def open_screen_recording_settings() -> None:
    if sys.platform != "darwin":
        raise SourceUnavailable("Screen Recording settings are available only on macOS")
    try:
        subprocess.run(["/usr/bin/open", _SETTINGS_URL], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise CaptureError("Could not open macOS Screen Recording settings") from error


class MacWindowSource:
    """Read only a selected window; pin its owner PID and recheck each capture."""

    def __init__(self, window_id: int, label: str | None = None) -> None:
        if isinstance(window_id, bool) or not isinstance(window_id, int) or not 0 < window_id <= 0xFFFFFFFF:
            raise SourceUnavailable("Select a valid macOS window ID")
        self._native = _get_native()
        self._window_id = window_id
        self._closed = False
        self._lock = threading.Lock()
        selected = self._current_window()
        self._pid = selected.pid
        self.label = label or f"{selected.app}: {selected.title or 'Window'}"
        self._check_permission()

    def _current_window(self) -> WindowInfo:
        for window in _normal_windows(self._native.window_records()):
            if window.window_id == self._window_id:
                return window
        raise SourceUnavailable("The selected window is closed, minimized, or no longer on screen")

    def _check_permission(self) -> None:
        if self._pid != os.getpid() and not self._native.screen_allowed():
            raise CapturePermissionError(
                "Enable Screen Recording for the app running Word Link Copilot, "
                "then restart it if macOS requires. Only the selected window will be read.",
            )

    def _validate_selection(self) -> None:
        if self._current_window().pid != self._pid:
            raise SourceUnavailable("The selected window changed owners; select the mirror window again")
        self._check_permission()

    def read(self) -> CapturedFrame:
        with self._lock:
            if self._closed:
                raise SourceUnavailable("This window capture source is closed")
            self._validate_selection()
            captured_at = time.monotonic()
            try:
                image = self._native.capture_window(self._window_id)
            except SourceUnavailable:
                self._validate_selection()
                raise
            # Reject a closed/minimized/reused window even if it changed during
            # the native call. Preserve the conservative acquisition timestamp:
            # a slow capture or metadata check must not make old pixels fresh.
            self._validate_selection()
            return CapturedFrame(image, captured_at)

    def close(self) -> None:
        with self._lock:
            self._closed = True

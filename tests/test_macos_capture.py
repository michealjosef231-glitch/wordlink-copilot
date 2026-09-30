from __future__ import annotations

import ctypes as ct
import os
import plistlib
from types import SimpleNamespace

import numpy as np
import pytest

from wordlink.capture import macos
from wordlink.capture.sources import CaptureError, CapturePermissionError, SourceUnavailable


def record(window_id=91, pid=None, **changes):
    value = {
        "kCGWindowNumber": window_id,
        "kCGWindowOwnerPID": os.getpid() + 10 if pid is None else pid,
        "kCGWindowOwnerName": "Mirror app",
        "kCGWindowName": "iPad",
        "kCGWindowLayer": 0,
        "kCGWindowIsOnscreen": True,
        "kCGWindowAlpha": 1.0,
        "kCGWindowBounds": {"X": -20, "Y": 30, "Width": 320, "Height": 480},
    }
    value.update(changes)
    return value


class FakeNative:
    def __init__(self):
        self.records = [record()]
        self.allowed = True
        self.requested = 0
        self.captured = []
        self.on_capture = None

    def window_records(self):
        return self.records

    def screen_allowed(self):
        return self.allowed

    def request_screen_access(self):
        self.requested += 1
        return True

    def capture_window(self, window_id):
        self.captured.append(window_id)
        if self.on_capture:
            self.on_capture()
        return np.full((20, 30, 3), (7, 35, 210), np.uint8)


@pytest.fixture
def native(monkeypatch):
    fake = FakeNative()
    monkeypatch.setattr(macos.sys, "platform", "darwin")
    monkeypatch.setattr(macos, "_get_native", lambda: fake)
    return fake


def test_picker_filters_normal_visible_windows_and_prefers_quicktime(native):
    native.records = [
        record(12),
        record(14, kCGWindowOwnerName="QuickTime Player", kCGWindowName=""),
        record(15, kCGWindowLayer=2),
        record(16, kCGWindowIsOnscreen=False),
        record(17, kCGWindowAlpha=0),
        record(18, kCGWindowBounds={"X": 0, "Y": 0, "Width": 0, "Height": 50}),
        record(19, kCGWindowBounds={"X": float("nan"), "Y": 0, "Width": 50, "Height": 50}),
        {"invalid": "metadata"},
    ]
    native.allowed = False
    windows = macos.list_windows()
    assert [window.window_id for window in windows] == [14, 12]
    assert windows[0].title == ""
    assert windows[0].bounds == (-20, 30, 320, 480)
    assert not macos.screen_recording_allowed()
    assert native.requested == 0


def test_permission_request_is_explicit_and_missing_title_does_not_grant_access(native):
    native.allowed = False
    native.records = [record(kCGWindowName="")]
    assert macos.list_windows()[0].title == ""
    with pytest.raises(CapturePermissionError, match="Enable Screen Recording"):
        macos.MacWindowSource(91)
    assert native.captured == []
    assert native.requested == 0
    assert macos.request_screen_recording()
    assert native.requested == 1


def test_own_process_window_can_capture_without_global_consent(native, monkeypatch):
    native.records = [record(pid=os.getpid())]
    native.allowed = False
    clock = {"now": 10.0}
    monkeypatch.setattr(macos.time, "monotonic", lambda: clock["now"])
    native.on_capture = lambda: clock.update(now=20.0)
    source = macos.MacWindowSource(91, "Test mirror")
    assert native.captured == []
    frame = source.read()
    assert frame.captured_at == 20.0
    assert frame.media_time is None
    assert source.label == "Test mirror"
    np.testing.assert_array_equal(frame.image[0, 0], [7, 35, 210])
    assert native.captured == [91]
    assert native.requested == 0


def test_permission_revocation_prevents_new_capture(native):
    source = macos.MacWindowSource(91)
    native.allowed = False
    with pytest.raises(CapturePermissionError):
        source.read()
    assert native.captured == []


@pytest.mark.parametrize("change", ["closed", "minimized", "new_owner"])
def test_unavailable_or_reused_window_does_not_capture(native, change):
    source = macos.MacWindowSource(91)
    if change == "closed":
        native.records = []
    elif change == "minimized":
        native.records[0]["kCGWindowIsOnscreen"] = False
    else:
        native.records[0]["kCGWindowOwnerPID"] += 1
    with pytest.raises(SourceUnavailable):
        source.read()
    assert native.captured == []


@pytest.mark.parametrize("change", ["closed", "new_owner", "revoked"])
def test_change_during_capture_discards_the_frame(native, change):
    source = macos.MacWindowSource(91)
    if change == "closed":
        native.on_capture = lambda: native.records.clear()
    elif change == "new_owner":
        native.on_capture = lambda: native.records[0].update(kCGWindowOwnerPID=os.getpid() + 20)
    else:
        native.on_capture = lambda: setattr(native, "allowed", False)
    expected = CapturePermissionError if change == "revoked" else SourceUnavailable
    with pytest.raises(expected):
        source.read()
    assert native.captured == [91]


def test_close_is_idempotent_and_closed_source_does_not_read(native):
    source = macos.MacWindowSource(91)
    source.close()
    source.close()
    with pytest.raises(SourceUnavailable, match="closed"):
        source.read()
    assert native.captured == []


@pytest.mark.parametrize("window_id", [0, -1, True, 1 << 32, "91"])
def test_invalid_window_id_cannot_capture_the_desktop(native, window_id):
    with pytest.raises(SourceUnavailable, match="valid macOS window ID"):
        macos.MacWindowSource(window_id)
    assert native.captured == []


class FakeCG:
    def __init__(self, context=True, transparent=False):
        self.created = None
        self.context = context
        self.transparent = transparent
        self.released = []
        self.backing = None

    def CGWindowListCreateImage(self, bounds, options, window_id, image_options):
        self.created = (bounds, options, window_id, image_options)
        return 111

    def CGImageGetWidth(self, image):
        return 3

    def CGImageGetHeight(self, image):
        return 2

    def CGColorSpaceCreateDeviceRGB(self):
        return 222

    def CGBitmapContextCreate(self, pointer, width, height, bits, stride, space, info):
        assert (width, height, bits, stride, space, info) == (3, 2, 8, 16, 222, macos._BGRA_BITMAP_INFO)
        self.backing = np.ctypeslib.as_array((ct.c_uint8 * (height * stride)).from_address(pointer)).reshape(height, stride)
        return 333 if self.context else None

    def CGContextDrawImage(self, context, bounds, image):
        self.backing[:] = 199  # Distinct padding must never become image pixels.
        for y in range(2):
            for x in range(3):
                self.backing[y, x * 4:x * 4 + 4] = [10 + x, 40 + y, 180 + x + y, 0 if self.transparent else 255]

    def CGContextRelease(self, context):
        self.released.append(context)
        self.backing[:] = 0  # Verify returned pixels own their memory.

    def CGColorSpaceRelease(self, space):
        self.released.append(space)

    def CGImageRelease(self, image):
        self.released.append(image)


def quartz_with(fake_cg):
    quartz = object.__new__(macos._Quartz)
    quartz.cg = fake_cg
    quartz.null_rect = macos._CGRect(macos._CGPoint(float("inf"), float("inf")), macos._CGSize(0, 0))
    return quartz


def test_known_bgra_format_handles_padding_and_captures_only_selected_id():
    cg = FakeCG()
    image = quartz_with(cg).capture_window(331)
    assert image.shape == (2, 3, 3)
    assert image.flags.c_contiguous
    assert image.dtype == np.uint8
    np.testing.assert_array_equal(image[0, 0], [10, 40, 180])
    np.testing.assert_array_equal(image[1, 2], [12, 41, 183])
    _, options, window_id, image_options = cg.created
    assert options == 1 << 3  # Exactly this window; never all/above/below.
    assert window_id == 331
    assert image_options == (1 << 0) | (1 << 4)
    assert cg.released == [333, 222, 111]


def test_failed_bitmap_allocation_releases_created_native_objects():
    cg = FakeCG(context=False)
    with pytest.raises(CaptureError, match="bitmap"):
        quartz_with(cg).capture_window(331)
    assert cg.released == [222, 111]


def test_transparent_unreadable_window_releases_native_objects():
    cg = FakeCG(transparent=True)
    with pytest.raises(SourceUnavailable, match="unavailable or protected"):
        quartz_with(cg).capture_window(331)
    assert cg.released == [333, 222, 111]


def test_cf_metadata_serialization_releases_copy_and_data():
    payload = ct.create_string_buffer(plistlib.dumps([record()], fmt=plistlib.FMT_BINARY))
    released = []
    quartz = object.__new__(macos._Quartz)
    quartz.cg = SimpleNamespace(CGWindowListCopyWindowInfo=lambda options, wid: 123)
    quartz.cf = SimpleNamespace(
        CFPropertyListCreateData=lambda *args: 456,
        CFDataGetLength=lambda data: len(payload.raw) - 1,
        CFDataGetBytePtr=lambda data: ct.addressof(payload),
        CFRelease=lambda pointer: released.append(pointer),
    )
    assert quartz.window_records() == [record()]
    assert released == [456, 123]


def test_cf_serialization_failure_releases_error_and_array():
    released = []

    def fail(allocator, array, format_, options, error):
        ct.cast(error, ct.POINTER(ct.c_void_p))[0] = 789
        return None

    quartz = object.__new__(macos._Quartz)
    quartz.cg = SimpleNamespace(CGWindowListCopyWindowInfo=lambda options, wid: 123)
    quartz.cf = SimpleNamespace(
        CFPropertyListCreateData=fail,
        CFRelease=lambda pointer: released.append(pointer.value if isinstance(pointer, ct.c_void_p) else pointer),
    )
    with pytest.raises(CaptureError, match="decode"):
        quartz.window_records()
    assert released == [789, 123]


def test_non_mac_helpers_do_not_load_native_frameworks(monkeypatch):
    monkeypatch.setattr(macos.sys, "platform", "linux")
    macos._get_native.cache_clear()
    monkeypatch.setattr(macos.ct, "CDLL", lambda path: pytest.fail("Native library loaded on non-Mac"))
    assert macos.list_windows() == []
    assert macos.screen_recording_allowed() is False
    assert macos.request_screen_recording() is False
    with pytest.raises(SourceUnavailable, match="only on macOS"):
        macos.MacWindowSource(91)
    with pytest.raises(SourceUnavailable, match="only on macOS"):
        macos.open_screen_recording_settings()


def test_settings_opens_screen_recording_pane_without_shell(native, monkeypatch):
    calls = []
    monkeypatch.setattr(macos.subprocess, "run", lambda arguments, **options: calls.append((arguments, options)))
    macos.open_screen_recording_settings()
    assert calls == [(["/usr/bin/open", macos._SETTINGS_URL], {"check": True, "capture_output": True})]


@pytest.mark.skipif(macos.sys.platform != "darwin" or os.environ.get("WORDLINK_NATIVE_CAPTURE_TEST") != "1",
                    reason="Opt-in native own-window test; no desktop or other apps are captured")
def test_native_own_tk_window_pixels_and_closed_window():
    import tkinter as tk
    import time

    before = {window.window_id for window in macos.list_windows()}
    root = tk.Tk()
    root.withdraw()
    window = tk.Toplevel(root)
    source = None
    try:
        title = f"Word Link capture fixture {os.getpid()}"
        window.title(title)
        window.geometry("220x180+80+80")
        canvas = tk.Canvas(window, width=220, height=180, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_rectangle(0, 0, 110, 90, fill="#ff0000", outline="")
        canvas.create_rectangle(110, 0, 220, 90, fill="#00ff00", outline="")
        canvas.create_rectangle(0, 90, 110, 180, fill="#0000ff", outline="")
        canvas.create_rectangle(110, 90, 220, 180, fill="#ffffff", outline="")
        for _ in range(10):
            root.update()
            time.sleep(.03)
        candidates = [window for window in macos.list_windows()
                      if window.pid == os.getpid() and (window.title == title or window.window_id not in before)]
        assert len(candidates) == 1, "New own-process fixture window was not identified uniquely"
        allowed = macos.screen_recording_allowed()
        source = macos.MacWindowSource(candidates[0].window_id, "Native pixel fixture")
        started = time.monotonic()
        frame = source.read()
        elapsed_ms = (time.monotonic() - started) * 1000
        image = frame.image
        assert 180 <= image.shape[0] <= 240 and image.shape[1] == 220
        red = (image[:, :, 2] > 220) & (image[:, :, 1] < 40) & (image[:, :, 0] < 40)
        green = (image[:, :, 1] > 220) & (image[:, :, 2] < 40) & (image[:, :, 0] < 40)
        blue = (image[:, :, 0] > 220) & (image[:, :, 1] < 40) & (image[:, :, 2] < 40)
        assert all(mask.sum() > 5000 for mask in (red, green, blue))
        red_y, red_x = np.nonzero(red)
        green_y, green_x = np.nonzero(green)
        blue_y, blue_x = np.nonzero(blue)
        assert np.median(red_y) < np.median(blue_y), "Native image rows were flipped"
        assert np.median(red_x) < np.median(green_x), "Native image columns were flipped"
        assert started <= frame.captured_at <= time.monotonic()
        print(f"native_pixels={image.shape}, BGR_red={np.median(image[red], axis=0)}, "
              f"BGR_blue={np.median(image[blue], axis=0)}, permission={allowed}, capture_ms={elapsed_ms:.1f}")
        window.destroy()
        # Keep the Tk/Cocoa event loop alive until WindowServer observes close.
        # Destroying the last root without pumping events leaves deferred work.
        for _ in range(10):
            root.update()
            time.sleep(.03)
        with pytest.raises(SourceUnavailable):
            source.read()
    finally:
        if source:
            source.close()
            source.close()
        try:
            root.destroy()
        except tk.TclError:
            pass

"""Exercise actual Tk, native own-window capture, and paced recording replay.

Own-window capture is a documented macOS exemption; this test does not grant
or bypass permission to capture other applications and does not connect an iPad.
"""

from __future__ import annotations

import json
import os
import time
import tkinter as tk

import cv2
from PIL import Image, ImageTk

from wordlink.capture.macos import MacWindowSource, list_windows, screen_recording_allowed
from wordlink.capture.replay import ReplaySource
from wordlink.paths import FIXTURES_DIR, ROOT
from wordlink.ui.app import create_app


def wait_for(root, predicate, message, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError(message)


def expected_board(label):
    return "".join(label["letters"]), tuple(dot for row in label["dots"] for dot in row)


def matches(app, label):
    letters, dots = expected_board(label)
    return (app.board is not None and "".join(app.board.letters) == letters
            and app.board.dots == dots and bool(app.ranked_words))


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    labels = json.loads((FIXTURES_DIR / "boards/labels.json").read_text())["boards"]
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = create_app(root)
    mirror = tk.Toplevel(root)
    mirror.title("Word Link native capture validation")
    mirror.geometry("512x732+1310+70")
    mirror.configure(bg="#007bca")
    panel = tk.Label(mirror, borderwidth=0, highlightthickness=0)
    panel.pack(fill="both", expand=True)
    image_ref = None
    measurements = []

    def display(label):
        nonlocal image_ref
        screenshot = Image.new("RGB", (512, 732), (0, 123, 202))
        with Image.open(FIXTURES_DIR / "boards" / label["file"]) as board:
            screenshot.paste(board.convert("RGB"), (64, 200))
        image_ref = ImageTk.PhotoImage(screenshot, master=root)
        panel.configure(image=image_ref)
        root.update()

    try:
        display(labels[0])
        windows = [window for window in list_windows()
                   if window.pid == os.getpid() and window.title == mirror.title()]
        assert len(windows) == 1, "The native validation mirror window must be selectable"
        app.refresh_windows()
        assert app.window_var.get() == "Choose an existing mirror window", (
            "Window discovery must not silently select another app for capture"
        )
        window = windows[0]
        # Save only our purpose-built board test window, never a desktop capture.
        probe = MacWindowSource(window.window_id)
        frame = probe.read()
        probe.close()
        cv2.imwrite(str(ROOT / "artifacts/native_capture.png"), frame.image)
        app.start_live(MacWindowSource(window.window_id))
        for index, label in enumerate(labels):
            started = time.monotonic()
            if index:
                display(label)
                wait_for(root, lambda: not app.ranked_words,
                         "Old suggestions remained after native board changed", timeout=1.5)
                assert not app.canvas.find_withtag("path")
            wait_for(root, lambda: matches(app, label),
                     f"Native capture did not recognize {label['file']}")
            root.update()
            assert app.canvas.find_withtag("path"), "Ready native board needs a numbered path"
            measurements.append({"fixture": label["file"],
                                 "ready_after_ms": round((time.monotonic() - started) * 1000, 1),
                                 "letters": "".join(app.board.letters), "dots": list(app.board.dots),
                                 "word": app.best_word_var.get()})
            print(json.dumps({"native_ready": measurements[-1]}), flush=True)
        selected = next(window for window in list_windows()
                        if window.pid == os.getpid() and window.title.startswith("Word Link Copilot"))
        capture = MacWindowSource(selected.window_id)
        cv2.imwrite(str(ROOT / "artifacts/live_assistant.png"), capture.read().image)
        capture.close()
        mirror.destroy()
        wait_for(root, lambda: app._live_state == "disconnected",
                 "Closing native source did not disconnect", timeout=3)
        assert not app.ranked_words and not app.canvas.find_withtag("path")
        # The source reaches end after 1.4s; enough for a complete settled read.
        app.start_live(ReplaySource(FIXTURES_DIR / "videos/reference.mp4", start=129))
        wait_for(root, lambda: app._live_state == "ended", "Replay end was not surfaced", timeout=8)
        assert not app.ranked_words
        app.start_live(ReplaySource(FIXTURES_DIR / "videos/reference.mp4", start=10))
        wait_for(root, lambda: matches(app, labels[0]), "Actual recording replay did not read labeled board")
        app.letter_vars[0].set("A")
        root.update()
        assert not app._live_requested and app._live_controller is None
        assert not app.ranked_words
        assert not errors, errors
        output = {"passed": True, "window": "Actual Tk GUI + CoreGraphics selected-window capture",
                  "native_capture": {"source": "own-process validation window",
                                     "screen_recording_allowed": screen_recording_allowed(),
                                     "pixel_shape": list(frame.image.shape), "boards": measurements},
                  "checks": ["native pixel capture", "64 labeled letters and dots", "automatic paths",
                             "clear during board change", "window-close disconnect clears suggestions",
                             "real recording replay", "replay end clears suggestions",
                             "manual editing stops live", "shutdown"],
                  "callback_errors": errors, "physical_ipad_tested": False}
        (ROOT / "artifacts/live_smoke.json").write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output), flush=True)
    finally:
        app.close()


if __name__ == "__main__":
    main()

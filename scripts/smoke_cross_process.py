"""Read a separate, purpose-built mirror process through the native backend.

Requires ordinary macOS Screen Recording consent. Never selects a webcam,
desktop, or user application; only the child process's known fixture window.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
from queue import Empty
import time
import tkinter as tk

from PIL import Image, ImageTk

from wordlink.capture.macos import MacWindowSource, list_windows, screen_recording_allowed
from wordlink.paths import FIXTURES_DIR, ROOT
from wordlink.ui.app import create_app

TITLE = "Word Link separate-process validation mirror"


def mirror_main(commands, acknowledgments):
    root = tk.Tk()
    root.title(TITLE)
    root.geometry("512x732+1290+55")
    root.configure(bg="#007bca")
    panel = tk.Label(root, borderwidth=0, highlightthickness=0, bg="#007bca")
    panel.pack(fill="both", expand=True)
    photo = None

    def receive():
        nonlocal photo
        try:
            token, filename, width = commands.get_nowait()
        except Empty:
            root.after(10, receive)
            return
        if filename == "close":
            root.destroy()
            return
        if filename == "minimize":
            root.iconify()
        elif filename == "restore":
            root.deiconify()
        else:
            image = Image.new("RGB", (512, 732), (0, 123, 202))
            if filename:
                with Image.open(FIXTURES_DIR / "boards" / filename) as board:
                    image.paste(board.convert("RGB"), (64, 200))
            height = round(width * 732 / 512)
            image = image.resize((width, height), Image.Resampling.LANCZOS)
            root.geometry(f"{width}x{height}+{min(1290, 1850-width)}+45")
            photo = ImageTk.PhotoImage(image, master=root)
            panel.configure(image=photo)
        root.update_idletasks()
        acknowledgments.put(token)
        root.after(10, receive)

    root.after(10, receive)
    root.mainloop()


def main():
    assert screen_recording_allowed(), "Grant normal Screen Recording consent before this cross-process test"
    labels = json.loads((FIXTURES_DIR / "boards/labels.json").read_text())["boards"]
    context = mp.get_context("spawn")
    commands, acknowledgments = context.Queue(), context.Queue()
    child = context.Process(target=mirror_main, args=(commands, acknowledgments))
    child.start()
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = create_app(root)
    results = []
    token = 0

    def wait_for(predicate, reason, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            root.update()
            assert child.is_alive(), "Validation mirror unexpectedly exited"
            if predicate():
                return
            time.sleep(.01)
        raise AssertionError(f"{reason}; live state={app._live_state}; "
                             f"status={app.live_source_var.get()}; "
                             f"mirror windows={[item for item in list_windows() if item.pid == child.pid]}")

    def send(filename, width=512):
        nonlocal token
        token += 1
        commands.put((token, filename, width))

        def acknowledged():
            try:
                return acknowledgments.get_nowait() == token
            except Empty:
                return False

        wait_for(acknowledged, "Mirror command did not render")

    def window():
        choices = [item for item in list_windows() if item.pid == child.pid and item.title == TITLE]
        assert len(choices) == 1, "Expected only the explicitly created validation mirror"
        assert choices[0].pid != os.getpid(), "This must exercise capture across processes"
        return choices[0]

    def matches(label):
        return (app.board is not None and app.board.letters == tuple("".join(label["letters"]))
                and app.board.dots == tuple(dot for row in label["dots"] for dot in row)
                and bool(app.ranked_words))

    try:
        send(labels[0]["file"])
        app.start_live(MacWindowSource(window().window_id))
        for index, label in enumerate(labels):
            started = time.monotonic()
            if index:
                send(label["file"])
                wait_for(lambda: not app.ranked_words, "Old words survived a changed board", 1.5)
            wait_for(lambda: matches(label), f"Cross-process recognition failed: {label['file']}")
            assert app.canvas.find_withtag("path")
            measurement = {"fixture": label["file"], "ready_after_ms": round((time.monotonic()-started)*1000, 1)}
            results.append(measurement)
            print(json.dumps(measurement), flush=True)
        send(None)
        wait_for(lambda: not app.ranked_words, "Missing grid left old recommendations", 1.5)
        assert not app.canvas.find_withtag("path")
        assert all(variable.get() == "" for variable in app.letter_vars)
        send(labels[0]["file"], 680)
        wait_for(lambda: matches(labels[0]), "Resized mirror did not recover")
        assert app.canvas.find_withtag("path")
        for _ in range(3):
            app.stop_live()
            assert not app.ranked_words and app._live_controller is None
            app.start_live(MacWindowSource(window().window_id))
            assert all(variable.get() == "" for variable in app.letter_vars)
            wait_for(lambda: matches(labels[0]), "Restart did not restore a fresh board")
        send("minimize")
        wait_for(lambda: not any(item.pid == child.pid and item.title == TITLE for item in list_windows()),
                 "WindowServer did not finish minimizing the validation mirror", 5)
        wait_for(lambda: app._live_state == "disconnected", "Minimized source did not disconnect", 3)
        assert not app.ranked_words and not app.canvas.find_withtag("path")
        assert all(variable.get() == "" for variable in app.letter_vars)
        send("restore")
        wait_for(lambda: any(item.pid == child.pid and item.title == TITLE for item in list_windows()),
                 "Restored mirror did not become selectable", 5)
        app.start_live(MacWindowSource(window().window_id))
        wait_for(lambda: matches(labels[0]), "Reconnect did not recover")
        assert not errors, errors
        output = {"passed": True, "source": "explicit separate-process fixture mirror",
                  "screen_recording_allowed": True, "boards": results,
                  "checks": ["64 labeled letters and dots", "numbered paths", "board-change clears words",
                             "missing grid clears words", "resized source recovers", "three stop/start cycles",
                             "minimize disconnect", "restore and reconnect", "zero Tk callback errors"],
                  "physical_ipad_tested": False}
        (ROOT / "artifacts").mkdir(exist_ok=True)
        (ROOT / "artifacts/cross_process_smoke.json").write_text(json.dumps(output, indent=2)+"\n")
        print(json.dumps(output), flush=True)
    finally:
        app.close()
        commands.put((0, "close", 0))
        child.join(3)
        if child.is_alive():
            child.terminate()
            child.join(3)
        commands.close()
        acknowledgments.close()


if __name__ == "__main__":
    main()

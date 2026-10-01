"""Verify stable live rendering and safe transitions in the real Tk window.

Inject independently recognized local fixtures as controller updates. This tests
the graphical display, not a physical device or native capture transport.
"""
from dataclasses import replace
import json
from time import monotonic, sleep
import tkinter as tk
from unittest.mock import patch

print("stable UI smoke: importing image libraries", flush=True)
import cv2
import numpy as np
from PIL import Image, ImageTk

from wordlink.capture.live import LiveUpdate
from wordlink.capture.sources import CapturedFrame
from wordlink.paths import DATA_DIR, FIXTURES_DIR, ROOT
from wordlink.solver.ranking import rank_words
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.ui.app import create_app
from wordlink.vision.board import recognize
from wordlink.vocabulary.policy import VocabularyPolicy


def settle_layout(root):
    """Allow geometry callbacks to finish before measuring repaint identity."""
    deadline = monotonic() + .12
    while monotonic() < deadline:
        root.update()
        sleep(.01)


def main():
    print("stable UI smoke: preparing real fixtures and local vocabulary", flush=True)
    trie = Trie((DATA_DIR / "words.txt").read_text(encoding="utf-8").splitlines())
    policy = VocabularyPolicy.from_directory(DATA_DIR)
    images = [cv2.copyMakeBorder(cv2.imread(str(FIXTURES_DIR / "boards" / name)),
                                32, 32, 32, 32, cv2.BORDER_CONSTANT,
                                value=(130, 65, 20))
              for name in ("frame_010.000.png", "frame_090.000.png")]
    reads = [recognize(image) for image in images]
    assert not any(read.warnings for read in reads)
    ranked = [tuple(rank_words(find_words(read.board, trie), policy)) for read in reads]
    assert all(len(words) >= 4 for words in ranked)

    print("stable UI smoke: opening Tk window", flush=True)
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = create_app(root)
    root.geometry("1240x760")
    app._live_requested = True
    app._live_label = "Purpose-built stable UI fixture"
    app._vocabulary_count = len(trie)
    sequence = 0
    clock = [100.0]

    def ready(index=0, shift=0, stale=False):
        nonlocal sequence
        sequence += 1
        clock[0] += .01
        read = reads[index]
        if shift:
            boxes = tuple((x + shift, y, width, height)
                          for x, y, width, height in read.board.boxes)
            read = replace(read, board=replace(read.board, boxes=boxes))
        image = np.roll(images[index], shift, axis=1) if shift else images[index]
        frame = CapturedFrame(image, clock[0] - (2 if stale else 0))
        app._apply_live_update(LiveUpdate("ready", "Stable fixture", frame, read,
                                        ranked[index], sequence=sequence))
        root.update()

    # Updates here are synthetic controller injections, not live captures.
    # Control only the UI freshness clock so cold native layout cannot age a
    # fixture. Advance it explicitly below to exercise the real expiry guard.
    ui_clock = patch("wordlink.ui.app.monotonic", side_effect=lambda: clock[0])
    ui_clock.start()
    try:
        settle_layout(root)
        app._set_play_view(True)
        settle_layout(root)
        # Warm Tk's lazily imported native image bridge before starting the
        # freshness-sensitive updates. Its first load can be slow on this Mac.
        warm_photo = ImageTk.PhotoImage(Image.new("RGB", (1, 1)), master=root)
        root.update()
        del warm_photo
        print("stable UI smoke: checking fresh updates and selection", flush=True)
        ready()
        app.select_candidate(1)
        root.update()
        chosen = app.ranked_words[1].found
        photo = app._photo
        canvas_items = app.canvas.find_all()
        buttons = tuple(app.alternative_buttons)
        entry_writes = []
        for variable in (*app.letter_vars, *app.dot_vars):
            variable.trace_add("write", lambda *_: entry_writes.append(True))

        for _ in range(20):
            ready()
            assert app._photo is photo and app.canvas.find_all() == canvas_items
            assert tuple(app.alternative_buttons) == buttons
            assert app.selected_index == 1 and app.best_word_var.get() == chosen.word
        assert not entry_writes, "Identical ready updates rewrote editable entries"
        for shift in (1, 2, 3):
            ready(shift=shift)
            assert app._photo is photo and app.canvas.find_all() == canvas_items
        ready(shift=4)
        assert app._photo is not photo and app.canvas.find_all() != canvas_items
        assert app._rendered_board.boxes == app.board.boxes
        assert app.selected_index == 1

        app._apply_live_update(LiveUpdate("waiting", "Checking changed board",
                                        CapturedFrame(images[0], clock[0])))
        root.update()
        assert not app.ranked_words and not app.canvas.find_withtag("path")
        assert all(not variable.get() for variable in app.letter_vars)
        held_canvas = app.canvas.find_all()
        for _ in range(5):
            app._apply_live_update(LiveUpdate("waiting", "Checking changed board",
                                            CapturedFrame(images[0], clock[0])))
            root.update()
            assert app.canvas.find_all() == held_canvas
        ready()
        assert app.selected_index == 1 and app.ranked_words[1].found == chosen
        ready(index=1)
        assert app.selected_index == 0
        assert app.best_word_var.get() == ranked[1][0].found.word

        settle_layout(root)
        assert app.play_view and all(not widget.winfo_ismapped() for widget in app._detail_widgets)
        assert len(app.alternative_buttons) == 3
        viewport_top = app.results_canvas.winfo_rooty()
        viewport_bottom = viewport_top + app.results_canvas.winfo_height()
        assert app.results_canvas.yview()[0] == 0
        for button in app.alternative_buttons:
            assert button.winfo_ismapped()
            assert viewport_top <= button.winfo_rooty()
            assert button.winfo_rooty() + button.winfo_height() <= viewport_bottom
        app.toggle_play_view()
        settle_layout(root)
        assert not app.play_view and all(widget.winfo_ismapped() for widget in app._detail_widgets)

        ready(index=1, stale=True)
        assert not app.ranked_words and not app.canvas.find_withtag("path")
        assert all(not variable.get() for variable in app.letter_vars)
        ready(index=1)
        clock[0] += 2
        root.after_cancel(app._poll_id)
        app._poll()
        assert not app.ranked_words and not app.canvas.find_withtag("path")
        assert all(not variable.get() for variable in app.letter_vars)
        assert not errors, errors
        result = {"passed": True, "window": "Real Tk GUI at 1240x760",
                  "identical_ready_updates": 20, "callback_errors": errors,
                  "checks": ["stable photo, canvas, candidate widgets and entries",
                             "selected alternative preserved", "small geometry jitter held",
                             "cumulative geometry shift repainted", "waiting clears paths immediately",
                             "repeated waiting does not rebuild canvas", "same board restores selection",
                             "different board resets best", "play view fits three alternatives",
                             "review restores details", "stale ready clears paths and entries",
                             "independent two-second clock advance expires displayed results"],
                  "freshness_clock": "Controlled only for injected fixture updates; explicitly advanced for expiry"}
        destination = ROOT / "artifacts/stable_ui_smoke.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    finally:
        app.close()
        ui_clock.stop()


if __name__ == "__main__":
    main()

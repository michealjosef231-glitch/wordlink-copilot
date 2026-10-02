"""Exercise real Tk preview pixels, stable overlays and freshness boundaries.

Uses local labeled fixtures and a controlled UI freshness clock. Throughput
measures GUI painting only; it is not a native capture or physical-iPad test.
"""
import json
from statistics import median
from time import monotonic, perf_counter, sleep
import tkinter as tk
from unittest.mock import patch

import cv2
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
    deadline = monotonic() + .15
    while monotonic() < deadline:
        root.update()
        sleep(.01)


def main():
    print("fluid preview smoke: preparing labeled fixtures", flush=True)
    images = [cv2.copyMakeBorder(cv2.imread(str(FIXTURES_DIR / "boards" / name)),
                                32, 32, 32, 32, cv2.BORDER_CONSTANT, value=(130, 65, 20))
              for name in ("frame_010.000.png", "frame_090.000.png")]
    read = recognize(images[0])
    assert not read.warnings
    trie = Trie((DATA_DIR / "words.txt").read_text(encoding="utf-8").splitlines())
    policy = VocabularyPolicy.from_directory(DATA_DIR)
    ranked = tuple(rank_words(find_words(read.board, trie), policy))
    assert len(ranked) >= 4
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = create_app(root)
    root.geometry("1240x760")
    app._live_requested = True
    app._live_label = "Purpose-built fluid preview fixture"
    clock = [100.0]

    def pixel():
        # Read back the actual Tk image buffer, not the Python input image.
        return tuple(root.tk.call(str(app._photo), "get", 3, 3))

    def preview(image, stale=False):
        clock[0] += .01
        app._apply_preview_frame(CapturedFrame(image, clock[0] - (2 if stale else 0)))
        root.update()

    with patch("wordlink.ui.app.monotonic", side_effect=lambda: clock[0]):
        try:
            settle_layout(root)
            app._set_play_view(True)
            settle_layout(root)
            warm = ImageTk.PhotoImage(Image.new("RGB", (1, 1)), master=root)
            root.update()
            del warm
            app._apply_live_update(LiveUpdate("ready", "Recognized local fixture",
                CapturedFrame(images[0], clock[0]), read, ranked, sequence=1))
            app.select_candidate(1)
            app._full_screenshot = True
            app._draw_preview()
            settle_layout(root)
            photo = app._photo
            canvas_ids = app.canvas.find_all()
            path_ids = app.canvas.find_withtag("path")
            assert path_ids
            buttons = tuple(app.alternative_buttons)
            choice = app.best_word_var.get()
            recognized_at = app._live_frame_at
            timings = []
            distinct_pixels = set()
            print("fluid preview smoke: painting 30 frames in the real Tk image", flush=True)
            started = perf_counter()
            for index in range(30):
                image = images[0].copy()
                bgr = (20 + index * 5, 90, 220 - index * 4)
                image[:24] = bgr  # Animate outside the recognized tile grid.
                before = perf_counter()
                preview(image)
                timings.append((perf_counter() - before) * 1000)
                observed = pixel()
                assert observed == bgr[::-1], (observed, bgr)
                distinct_pixels.add(observed)
                assert app._photo is photo
                assert app.canvas.find_all() == canvas_ids
                assert app.canvas.find_withtag("path") == path_ids
                assert tuple(app.alternative_buttons) == buttons
                assert app.selected_index == 1 and app.best_word_var.get() == choice
                assert app._live_frame_at == recognized_at
            elapsed = perf_counter() - started
            assert len(distinct_pixels) == 30

            held_pixel, held_at = pixel(), app._image_at
            preview(images[1])
            assert pixel() == held_pixel and app._image_at == held_at
            assert app.canvas.find_withtag("path") == path_ids
            preview(images[0], stale=True)
            assert pixel() == held_pixel and app._image_at == held_at

            app._apply_live_update(LiveUpdate("waiting", "Board changed",
                                             CapturedFrame(images[0], clock[0])))
            root.update()
            assert not app.ranked_words and not app.canvas.find_withtag("path")
            changed = images[1].copy()
            changed[:24] = (180, 20, 60)
            preview(changed)
            assert pixel() == (60, 20, 180)
            assert app._image.size == (changed.shape[1], changed.shape[0])
            assert not app.canvas.find_withtag("path")

            clock[0] += .01
            app._apply_live_update(LiveUpdate("ready", "Fresh recognized fixture",
                CapturedFrame(images[0], clock[0]), read, ranked, sequence=2))
            root.update()
            recognized_at = app._live_frame_at
            for _ in range(3):
                clock[0] += .35
                preview(images[0])
            assert app._live_frame_at == recognized_at
            clock[0] = recognized_at + 1.51
            root.after_cancel(app._poll_id)
            app._poll()
            root.update()
            assert not app.ranked_words and not app.canvas.find_withtag("path")
            assert not errors, errors
            result = {"passed": True, "scope": "Real Tk 1240x760; injected fixture frames",
                      "frames_painted": 30, "distinct_Tk_pixels": len(distinct_pixels),
                      "median_paint_ms": round(median(timings), 2),
                      "max_paint_ms": round(max(timings), 2),
                      "unpaced_paint_fps": round(30 / elapsed, 1),
                      "checks": ["visible Tk pixels changed without replacing image, canvas, paths or buttons",
                                 "selected alternative preserved", "changed board held beneath old paths",
                                 "changed preview flows after waiting clears paths", "stale preview ignored",
                                 "preview never renews recognized word timestamp", "word freshness still expires"],
                      "callback_errors": errors}
            destination = ROOT / "artifacts/fluid_preview_smoke.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result), flush=True)
        finally:
            app.close()


if __name__ == "__main__":
    main()

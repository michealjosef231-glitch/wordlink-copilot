"""Exercise the real Tk window, worker, corrections, navigation, and shutdown."""
import json
import time
import tkinter as tk
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from wordlink.paths import FIXTURES_DIR, ROOT
from wordlink.ui.app import create_app


def wait(root, app, limit=30):
    deadline = time.monotonic() + limit
    root.update()
    while app.busy:
        if time.monotonic() >= deadline:
            raise AssertionError("UI analysis did not complete")
        root.update()
        time.sleep(.02)
    root.update()


def main():
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = create_app(root)
    try:
        first = FIXTURES_DIR / "boards/frame_010.000.png"
        app.open_image(first)
        wait(root, app)
        assert app.board is not None and "".join(app.board.letters) == "NOAIAERNGLUTGNOV"
        assert app.ranked_words and app.best_word_var.get() == app.ranked_words[0].found.word
        assert len(app.canvas.find_withtag("path")) > 0
        assert app.dictionary_var.get().startswith("Dictionary: UNKNOWN")
        app.select_candidate(1)
        assert app.selected_index == 1
        assert app.best_word_var.get() == app.ranked_words[1].found.word
        app.toggle_view()
        root.update()
        app.select_candidate(0)
        original = app.board
        app.dot_vars[0].set("bad")
        app.solve_corrected()
        assert app.status_var.get() == "CHECK ENTRIES"
        assert app.board == original
        app.dot_vars[0].set("1")
        app.solve_corrected()
        wait(root, app)
        assert app.last_result.edited
        app.open_image(FIXTURES_DIR / "boards/frame_090.000.png")
        wait(root, app)
        assert "".join(app.board.letters) == "IESVHSNEUTGYWROE"
        from wordlink.vision.board import recognize
        uncertain = replace(recognize(first), warnings=("Tile 1: uncertain letter N",))
        with patch("wordlink.ui.app.recognize", return_value=uncertain):
            app.open_image(first)
            wait(root, app)
        assert app.status_var.get() == "REVIEW NEEDED"
        assert "Solve edited board" in app.path_var.get()
        assert app.board == uncertain.board
        assert not app.ranked_words and not app.canvas.find_withtag("path")
        app.solve_corrected()
        wait(root, app)
        assert app.last_result.edited and app.ranked_words
        assert not errors, errors
        output = {
            "window": "Tk actual GUI", "best_word": app.best_word_var.get(),
            "candidate_count": len(app.ranked_words), "board": "".join(app.board.letters),
            "callback_errors": errors, "passed": True,
            "checks": ["screenshot worker", "detected board", "numbered paths", "unknown acceptance",
                       "alternatives", "full/cropped view", "invalid edit rejection", "manual solve", "second screenshot",
                       "uncertain screenshot holds paths until manual confirmation"],
        }
        destination = ROOT / "artifacts/ui_smoke.json"
        destination.write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output), flush=True)
    finally:
        app.close()


if __name__ == "__main__":
    main()

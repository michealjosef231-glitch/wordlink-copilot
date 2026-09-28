import json

import numpy as np

from wordlink.cli import main


def test_cli_manual_board_writes_paths_and_honest_score_status(tmp_path):
    output = tmp_path / "board.json"
    assert main(["board", "NOAI AERN GLUT GNOV", "--dots", "1 2 2 2 2 1 1 1 3 1 2 1 3 1 2 4",
                 "--json", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["legal_paths"]
    assert "uncalibrated" in result["scoring"]
    assert all(word["status"] == "unknown" for word in result["recommendations"])
    assert result["recommendations"][0]["confidence_band"] == "B"


def test_cli_invalid_board_fails_with_no_partial_export(tmp_path):
    output = tmp_path / "invalid.json"
    assert main(["board", "SHORT", "--dots", "1 2 3", "--json", str(output)]) == 2
    assert not output.exists()


def test_recording_pipeline_waits_skips_bad_reads_and_deduplicates(monkeypatch):
    from wordlink.capture import analyze
    from wordlink.capture.video import VideoInfo
    from wordlink.model import Board, Recognition
    from wordlink.solver.trie import Trie
    from wordlink.vocabulary.policy import VocabularyPolicy

    image = np.zeros((80, 80, 3), dtype=np.uint8)
    board = Board(tuple("NOAIAERNGLUTGNOV"), (1,) * 16)
    boxes = tuple((i % 4 * 20, i // 4 * 20, 18, 18) for i in range(16))
    monkeypatch.setattr(analyze, "video_info", lambda _: VideoInfo(4, 32, 80, 80))
    monkeypatch.setattr(analyze, "iter_frames", lambda *_: iter([(float(i), image) for i in range(9)]))
    monkeypatch.setattr(analyze, "detect_tiles", lambda _: boxes)
    attempts = 0

    def recognize(_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("Unreadable falling glyph")
        return Recognition(board, (), 1.0)

    monkeypatch.setattr(analyze, "recognize", recognize)
    result = analyze.analyze_recording("synthetic.mp4", Trie(["LEARN"]), VocabularyPolicy())
    assert attempts == 2
    assert len(result["boards"]) == 1
    assert result["boards"][0]["status"] == "solved"
    assert result["counts"]["missing_or_moving_tiles"] == 1
    assert result["diagnostic_examples"][0]["reason"] == "Unreadable falling glyph"

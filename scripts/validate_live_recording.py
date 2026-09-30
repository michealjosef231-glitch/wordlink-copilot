"""Run the original recording through the live controller at normal playback speed."""

from __future__ import annotations

import json
from time import monotonic, sleep

from wordlink.capture.live import LiveAssistant
from wordlink.capture.replay import ReplaySource
from wordlink.cli import dictionary_trie
from wordlink.paths import DATA_DIR, FIXTURES_DIR, ROOT
from wordlink.vocabulary.policy import VocabularyPolicy


def main():
    labels = json.loads((FIXTURES_DIR / "boards/labels.json").read_text())["boards"]
    expected = {label["timestamp_seconds"]: (
        "".join(label["letters"]), tuple(dot for row in label["dots"] for dot in row)
    ) for label in labels}
    matched = set()
    first_ready_at = {}
    boards = {}
    states = {}
    ages = []
    reads = []
    controller = LiveAssistant(ReplaySource(FIXTURES_DIR / "videos/reference.mp4"),
                               dictionary_trie(), VocabularyPolicy.from_directory(DATA_DIR))
    started = monotonic()
    controller.start()
    deadline = started + 180
    last_progress = started
    ended = False
    try:
        while monotonic() < deadline:
            update = controller.poll()
            if update is not None:
                states[update.state] = states.get(update.state, 0) + 1
                if update.state != "ready":
                    assert not update.ranked_words, "Non-ready state carried stale suggestions"
                if update.state == "ready":
                    assert update.recognition is not None and not update.recognition.warnings
                    assert update.frame is not None
                    age = (monotonic() - update.frame.captured_at) * 1000
                    assert 0 <= age <= 1500, "A ready frame exceeded the freshness limit"
                    ages.append(age)
                    board = update.recognition.board
                    key = ("".join(board.letters), board.dots)
                    if key not in boards:
                        for candidate in update.ranked_words:
                            found = candidate.found
                            assert len(set(found.path)) == len(found.path)
                            assert "".join(board.letters[index] for index in found.path) == found.word
                            assert sum(board.dots[index] for index in found.path) == found.dot_sum
                            for a, b in zip(found.path, found.path[1:]):
                                assert max(abs(a // 4 - b // 4), abs(a % 4 - b % 4)) == 1
                        boards[key] = {"media_time": update.frame.media_time,
                                       "letters": key[0], "dots": list(board.dots),
                                       "candidates": len(update.ranked_words),
                                       "best": update.ranked_words[0].found.word if update.ranked_words else None,
                                       "compute_ms": round(update.elapsed_ms, 1)}
                        reads.append(update.elapsed_ms)
                        print(json.dumps({"new_live_board": boards[key]}), flush=True)
                    for timestamp, labeled in expected.items():
                        # The player may be swiping at the exact labeled frame.
                        # A board may settle before or after that instant; its
                        # exact sixteen letters and dots are the real oracle.
                        if key == labeled:
                            matched.add(timestamp)
                            first_ready_at.setdefault(timestamp, update.frame.media_time)
                elif update.state == "ended":
                    ended = True
                    break
                elif update.state in {"permission", "disconnected", "error"}:
                    raise AssertionError(f"Live replay failed: {update.message}")
            if monotonic() - last_progress >= 15:
                print(json.dumps({"elapsed_seconds": round(monotonic() - started, 1),
                                  "unique_boards": len(boards), "labeled_times_matched": sorted(matched)}), flush=True)
                last_progress = monotonic()
            sleep(.015)
        assert ended, "The complete live replay did not end within its deadline"
        assert matched == set(expected), f"Missing independently labeled times: {set(expected) - matched}"
        sorted_ages = sorted(ages)
        output = {"passed": True, "source": "original recording, real-time replay",
                  "elapsed_seconds": round(monotonic() - started, 2),
                  "unique_boards": len(boards), "boards": list(boards.values()), "updates_by_state": states,
                  "labeled_times_matched": sorted(matched),
                  "label_board_first_ready_at_media_time": first_ready_at,
                  "letters_and_dots_validated": 64,
                  "ready_frame_age_ms": {"median": round(sorted_ages[len(sorted_ages) // 2], 1),
                                         "maximum": round(max(ages), 1)},
                  "unique_board_compute_ms": [round(value, 1) for value in reads],
                  "physical_ipad_tested": False}
        (ROOT / "artifacts").mkdir(exist_ok=True)
        (ROOT / "artifacts/live_recording_validation.json").write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output), flush=True)
    finally:
        controller.stop(timeout=1)


if __name__ == "__main__":
    main()

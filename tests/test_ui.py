"""Validation that protects corrected boards and screenshot path coordinates."""

import pytest

from wordlink.ui.app import crop_bounds, live_ready_is_fresh, parse_board_entries


def test_manual_entries_normalize_letters_and_preserve_screenshot_boxes():
    boxes = tuple((column * 100, row * 100, 90, 90) for row in range(4) for column in range(4))
    board = parse_board_entries([" a ", *list("BCDEFGHIJKLMNOP")], ["0", " 2 ", *["1"] * 14], boxes)
    assert board.letters == tuple("ABCDEFGHIJKLMNOP")
    assert board.dots == (0, 2, *[1] * 14)
    assert board.boxes == boxes


@pytest.mark.parametrize("letter", ["", "AB", "1", "é"])
def test_manual_entries_report_the_invalid_tile(letter):
    letters = list("ABCDEFGHIJKLMNOP")
    letters[6] = letter
    with pytest.raises(ValueError, match="Tile 7"):
        parse_board_entries(letters, ["1"] * 16)


@pytest.mark.parametrize("count", ["", "1.5", "-1", "11", "٢"])
def test_manual_entries_reject_non_count_dot_values(count):
    dots = ["1"] * 16
    dots[2] = count
    with pytest.raises(ValueError, match="Tile 3"):
        parse_board_entries(list("ABCDEFGHIJKLMNOP"), dots)


def test_manual_entries_require_the_whole_board():
    with pytest.raises(ValueError, match="16 tiles"):
        parse_board_entries(["A"] * 15, ["1"] * 16)


def test_board_crop_stays_inside_the_screenshot():
    bounds = crop_bounds((100, 80), ((-5, 4, 50, 40), (50, 45, 60, 40)))
    assert bounds == (0, 0, 100, 80)


def test_board_crop_keeps_all_tile_centers():
    boxes = tuple((300 + column * 75, 500 + row * 75, 70, 70) for row in range(4) for column in range(4))
    left, top, right, bottom = crop_bounds((1080, 1920), boxes)
    assert left < 300 < right and top < 500 < bottom
    assert all(left < x + width / 2 < right and top < y + height / 2 < bottom for x, y, width, height in boxes)


def test_missing_boxes_keep_the_full_source_image():
    assert crop_bounds((1080, 1920), ()) == (0, 0, 1080, 1920)


@pytest.mark.parametrize("state", ["waiting", "reading", "review", "permission", "disconnected", "ended", "error", "stopped"])
def test_only_ready_live_frames_allow_visible_suggestions(state):
    assert not live_ready_is_fresh(state, captured_at=100.0, now=100.1)


def test_live_suggestions_expire_even_without_a_worker_update():
    assert live_ready_is_fresh("ready", captured_at=100.0, now=100.0)
    assert live_ready_is_fresh("ready", captured_at=100.0, now=101.5)
    assert not live_ready_is_fresh("ready", captured_at=100.0, now=101.501)


@pytest.mark.parametrize("captured_at, now", [(None, 100.0), (101.0, 100.0), (float("nan"), 100.0), (100.0, float("inf"))])
def test_missing_or_invalid_live_frame_time_hides_suggestions(captured_at, now):
    assert not live_ready_is_fresh("ready", captured_at, now)


def test_uncertain_screenshot_holds_words_until_explicit_manual_solve(monkeypatch):
    from dataclasses import replace
    from threading import Event
    import wordlink.ui.app as ui
    from wordlink.paths import FIXTURES_DIR
    from wordlink.solver.trie import Trie
    from wordlink.vocabulary.policy import VocabularyPolicy
    from wordlink.vision.board import recognize

    path = FIXTURES_DIR / "boards/frame_010.000.png"
    uncertain = replace(recognize(path), warnings=("Tile 1: uncertain letter N",))
    monkeypatch.setattr(ui, "recognize", lambda _: uncertain)
    app = object.__new__(ui.WordLinkApp)
    app._vocabulary_count = 3
    app._trie = Trie(["TRAIN", "NOR", "NOT"])
    app._policy = VocabularyPolicy()
    outcome = app._analyze_screenshot(path, Event())
    assert outcome.board == uncertain.board and outcome.recognition.warnings
    assert not outcome.ranked_words and outcome.error is None
    confirmed = app._solve_board(outcome.board, outcome.image, Event())
    assert confirmed.edited and confirmed.ranked_words and confirmed.error is None

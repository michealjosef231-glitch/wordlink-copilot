from __future__ import annotations

import json
from pathlib import Path

import pytest

from wordlink.model import Board, FoundWord
from wordlink.solver.ranking import rank_words
from wordlink.solver.scoring import DEFAULT_PROFILE, ScoringProfile, count_turns, estimate_execution_seconds, proxy_score
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.vocabulary.policy import VocabularyPolicy


def board_at(letters: dict[int, str], dots: dict[int, int] | None = None) -> Board:
    return Board(
        tuple(letters.get(index, "X") for index in range(16)),
        tuple((dots or {}).get(index, 1) for index in range(16)),
    )


def test_trie_normalizes_entries_and_reuses_prefixes() -> None:
    trie = Trie([" cat ", "CAT", "CATS", "can't", "foo-bar", "", "CAFÉ", "ß"])
    assert len(trie) == 2
    assert "cat" in trie
    assert "CATS" in trie
    assert "CA" not in trie
    assert trie.has_prefix("ca")
    assert trie.has_prefix("")
    assert not trie.has_prefix("DO")
    assert not trie.has_prefix("C@")


def test_diagonal_neighbors_are_legal() -> None:
    found = find_words(board_at({0: "C", 5: "A", 10: "T"}), Trie(["CAT"]))
    assert found == [FoundWord("CAT", (0, 5, 10), 3)]


def test_row_boundary_does_not_wrap() -> None:
    found = find_words(board_at({3: "C", 4: "A", 5: "T"}), Trie(["CAT"]))
    assert found == []


def test_tile_cannot_be_reused_even_when_a_letter_repeats_in_the_word() -> None:
    board = board_at({0: "A", 1: "B"})
    assert find_words(board, Trie(["ABA", "ABAB"]), min_length=2) == []
    assert find_words(board, Trie(["AB"]), min_length=2) == [FoundWord("AB", (0, 1), 2)]


def test_separate_tiles_with_the_same_letter_can_form_repeated_letter_words() -> None:
    board = board_at({0: "A", 1: "B", 2: "A"})
    assert find_words(board, Trie(["ABA"])) == [
        FoundWord("ABA", (0, 1, 2), 3),
        FoundWord("ABA", (2, 1, 0), 3),
    ]


def test_all_paths_are_retained_including_different_dot_sums() -> None:
    board = board_at({0: "C", 1: "A", 2: "C", 5: "T"}, {0: 1, 1: 2, 2: 6, 5: 3})
    assert find_words(board, Trie(["CAT"])) == [
        FoundWord("CAT", (0, 1, 5), 6),
        FoundWord("CAT", (2, 1, 5), 11),
    ]


def test_minimum_length_and_impossible_length() -> None:
    board = board_at({0: "A", 1: "T", 2: "E", 3: "S"})
    trie = Trie(["A", "AT", "ATE", "ATES"])
    assert [found.word for found in find_words(board, trie)] == ["ATE", "ATES"]
    assert [found.word for found in find_words(board, trie, 4)] == ["ATES"]
    assert [found.word for found in find_words(board, trie, 1)] == ["A", "AT", "ATE", "ATES"]
    assert find_words(board, trie, 17) == []
    for invalid in (0, -1, True, 2.5):
        with pytest.raises(ValueError, match="positive integer"):
            find_words(board, trie, invalid)


def test_search_is_deterministic_and_every_returned_path_is_legal() -> None:
    board = Board(tuple("CATSRATEDOGLINKS"), tuple(range(4)) * 4)
    words = ["CAT", "CATS", "RATE", "RATES", "DOG", "DOGS", "INK", "LINK", "RAT", "TAR"]
    first = find_words(board, Trie(words))
    assert first
    assert first == find_words(board, Trie(reversed(words)))
    assert first == sorted(first, key=lambda found: (found.word, found.path))
    for found in first:
        assert len(found.path) == len(found.word)
        assert len(set(found.path)) == len(found.path)
        assert "".join(board.letters[index] for index in found.path) == found.word
        assert sum(board.dots[index] for index in found.path) == found.dot_sum
        for start, end in zip(found.path, found.path[1:]):
            assert max(abs(start // 4 - end // 4), abs(start % 4 - end % 4)) == 1


def test_ranking_selects_one_best_path_and_is_independent_of_input_order() -> None:
    found = [
        FoundWord("CAT", (0, 1, 5), 6),
        FoundWord("CAT", (2, 1, 5), 11),
        FoundWord("DOG", (8, 9, 10), 3),
        FoundWord("DOG", (8, 9, 10), 3),
    ]
    ranked = rank_words(found)
    assert len(ranked) == 2
    assert ranked == rank_words(list(reversed(found)))
    assert ranked[0].found == found[1]
    assert ranked[0].status == "unknown"
    assert ranked[0].proxy_score == 33.0
    assert ranked[0].estimated_seconds == pytest.approx(0.60)
    assert ranked[0].utility == pytest.approx(55.0)


def test_ranking_prefers_shorter_gestures_on_equal_dot_paths_and_stable_ties() -> None:
    straight = FoundWord("CAT", (0, 1, 2), 3)
    turning = FoundWord("CAT", (0, 1, 5), 3)
    tied = FoundWord("CAT", (4, 5, 6), 3)
    ranked = rank_words([turning, tied, straight])
    assert ranked[0].found == straight
    assert count_turns(straight.path) == 0
    assert count_turns(turning.path) == 1
    assert estimate_execution_seconds(straight) < estimate_execution_seconds(turning)
    assert proxy_score(straight) == 9.0


def test_confirmed_words_are_prioritized_and_rejected_words_are_excluded() -> None:
    policy = VocabularyPolicy(frozenset({"DOG"}), frozenset({"CAT"}))
    found = [FoundWord("CAT", (0, 1, 2), 30), FoundWord("RAT", (4, 5, 6), 20), FoundWord("DOG", (8, 9, 10), 1)]
    ranked = rank_words(found, policy)
    assert [candidate.found.word for candidate in ranked] == ["DOG", "RAT"]
    assert [candidate.status for candidate in ranked] == ["confirmed", "unknown"]


def test_bands_prefer_confirmed_then_common_without_dropping_rare_words() -> None:
    policy = VocabularyPolicy(
        confirmed=frozenset({"DOG"}),
        rejected=frozenset({"RAT"}),
        common_words=frozenset({"CAT", "RAT"}),
    )
    found = [
        FoundWord("HISTOGEN", (0, 1, 2, 3, 7, 11, 15, 14), 30),
        FoundWord("CAT", (0, 1, 2), 2),
        FoundWord("DOG", (8, 9, 10), 1),
        FoundWord("RAT", (4, 5, 6), 30),
    ]
    ranked = rank_words(found, policy)
    assert [candidate.found.word for candidate in ranked] == ["DOG", "CAT", "HISTOGEN"]
    assert [candidate.confidence_band for candidate in ranked] == ["A", "B", "C"]
    assert [candidate.status for candidate in ranked] == ["confirmed", "unknown", "unknown"]
    assert ranked[2].utility > ranked[1].utility > ranked[0].utility
    assert ranked == rank_words(list(reversed(found)), policy)


def test_persisted_profile_matches_default_and_is_explicitly_uncalibrated() -> None:
    directory = Path(__file__).resolve().parents[1] / "data"
    profile = ScoringProfile.from_file(directory / "scoring_profile.json")
    assert profile == DEFAULT_PROFILE
    assert profile.calibrated is False
    assert rank_words([FoundWord("CAT", (0, 1, 2), 3)], profile=profile)


def test_scoring_profile_refuses_false_calibration_and_invalid_coefficients(tmp_path: Path) -> None:
    original = Path(__file__).resolve().parents[1] / "data" / "scoring_profile.json"
    data = json.loads(original.read_text())
    data["calibrated"] = True
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="uncalibrated"):
        ScoringProfile.from_file(path)
    for invalid in (-1, float("inf"), True, None):
        with pytest.raises(ValueError):
            ScoringProfile(seconds_per_tile=invalid)
    with pytest.raises(ValueError, match="positive"):
        ScoringProfile(seconds_per_tile=0)

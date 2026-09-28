import json

import pytest

from wordlink.paths import FIXTURES_DIR
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.vision.board import recognize


CASES = json.loads((FIXTURES_DIR / "boards/labels.json").read_text())["boards"]


@pytest.mark.parametrize("case", CASES, ids=[case["file"] for case in CASES])
def test_all_letters_and_dots_match_independent_recording_labels(case):
    read = recognize(FIXTURES_DIR / "boards" / case["file"])
    assert read.board.letters == tuple("".join(case["letters"]))
    assert read.board.dots == tuple(value for row in case["dots"] for value in row)
    assert len(read.tiles) == 16
    assert not read.warnings


def test_first_board_has_the_expected_learn_path():
    read = recognize(FIXTURES_DIR / "boards" / CASES[0]["file"])
    found = find_words(read.board, Trie(["LEARN"]))
    assert any(word.path == (9, 5, 2, 6, 7) for word in found)
    for word in found:
        assert len(word.path) == len(set(word.path))
        assert "".join(read.board.letters[index] for index in word.path) == "LEARN"
        for start, end in zip(word.path, word.path[1:]):
            assert max(abs(start // 4 - end // 4), abs(start % 4 - end % 4)) == 1

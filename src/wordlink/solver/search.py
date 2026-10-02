"""Exact eight-neighbor search on a 4x4 board without reusing a tile."""

from __future__ import annotations

from wordlink.model import Board, FoundWord
from wordlink.solver.trie import Trie, TrieNode


def _neighbors(index: int) -> tuple[int, ...]:
    row, column = divmod(index, 4)
    return tuple(
        other_row * 4 + other_column
        for other_row in range(max(0, row - 1), min(4, row + 2))
        for other_column in range(max(0, column - 1), min(4, column + 2))
        if (other_row, other_column) != (row, column)
    )


NEIGHBORS = tuple(_neighbors(index) for index in range(16))


def find_words(board: Board, trie: Trie, min_length: int = 3) -> list[FoundWord]:
    """Return every legal dictionary path in deterministic word/path order.

    Different paths for the same word are retained: their dot sums and gesture
    estimates can differ. Trie pruning stops branches that cannot form a word.
    """
    if isinstance(min_length, bool) or not isinstance(min_length, int) or min_length < 1:
        raise ValueError("Minimum word length must be a positive integer")
    if min_length > sum(map(len, board.letters)):
        return []

    results: list[FoundWord] = []
    path: list[int] = []
    letters = board.letters
    dots = board.dots

    def advance(node: TrieNode, token: str) -> TrieNode | None:
        # A QU tile consumes both trie edges while visiting one physical tile.
        for letter in token:
            node = node.children.get(letter)
            if node is None:
                return None
        return node

    def visit(index: int, node: TrieNode, used: int, dot_sum: int) -> None:
        path.append(index)
        used |= 1 << index
        dot_sum += dots[index]
        if node.word is not None and len(node.word) >= min_length:
            results.append(FoundWord(node.word, tuple(path), dot_sum))
        for neighbor in NEIGHBORS[index]:
            if used & (1 << neighbor):
                continue
            child = advance(node, letters[neighbor])
            if child is not None:
                visit(neighbor, child, used, dot_sum)
        path.pop()

    for index, letter in enumerate(letters):
        child = advance(trie.root, letter)
        if child is not None:
            visit(index, child, 0, 0)
    results.sort(key=lambda found: (found.word, found.path))
    return results

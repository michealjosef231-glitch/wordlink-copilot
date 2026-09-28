"""Reusable local prefix dictionary; membership is not game acceptance."""

from __future__ import annotations

from collections.abc import Iterable


def _normalize(word: str) -> str:
    stripped = word.strip()
    if not stripped or not stripped.isascii() or not stripped.isalpha():
        return ""
    return stripped.upper()


class TrieNode:
    __slots__ = ("children", "word")

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.word: str | None = None


class Trie:
    """Build once and reuse across boards. Nonalphabetic entries are ignored."""

    def __init__(self, words: Iterable[str]) -> None:
        self.root = TrieNode()
        self.word_count = 0
        for entry in words:
            word = _normalize(entry)
            if not word:
                continue
            node = self.root
            for letter in word:
                child = node.children.get(letter)
                if child is None:
                    child = TrieNode()
                    node.children[letter] = child
                node = child
            if node.word is None:
                node.word = word
                self.word_count += 1

    def __len__(self) -> int:
        return self.word_count

    def __contains__(self, word: str) -> bool:
        normalized = _normalize(word)
        if not normalized:
            return False
        node = self._lookup(normalized)
        return node is not None and node.word is not None

    def has_prefix(self, prefix: str) -> bool:
        if not prefix.strip():
            return True
        normalized = _normalize(prefix)
        return bool(normalized) and self._lookup(normalized) is not None

    def _lookup(self, text: str) -> TrieNode | None:
        node = self.root
        for letter in text:
            node = node.children.get(letter)
            if node is None:
                return None
        return node

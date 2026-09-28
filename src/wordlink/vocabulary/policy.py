"""Read-only game verdicts and optional common-word membership.

Only user-observed outcomes belong in accepted/rejected ledgers. A common-word
list cannot establish game acceptance. Loading never creates a verdict or
writes a file. Rejection wins if a ledger is inconsistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

VocabularyStatus = Literal["confirmed", "rejected", "unknown"]
ConfidenceBand = Literal["A", "B", "C"]


def _normalize(word: str) -> str:
    stripped = word.strip()
    if not stripped or not stripped.isascii() or not stripped.isalpha():
        return ""
    return stripped.upper()


def _read_ledger(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    words = (_normalize(line) for line in path.read_text(encoding="utf-8").splitlines())
    return frozenset(word for word in words if word)


@dataclass(frozen=True)
class VocabularyPolicy:
    confirmed: frozenset[str] = frozenset()
    rejected: frozenset[str] = frozenset()
    common_words: frozenset[str] = frozenset()

    @classmethod
    def from_directory(cls, directory: Path) -> VocabularyPolicy:
        return cls(
            confirmed=_read_ledger(directory / "accepted.txt"),
            rejected=_read_ledger(directory / "rejected.txt"),
            common_words=_read_ledger(directory / "common.txt"),
        )

    def status(self, word: str) -> VocabularyStatus:
        normalized = _normalize(word)
        if normalized in self.rejected:
            return "rejected"
        if normalized in self.confirmed:
            return "confirmed"
        return "unknown"

    def is_common(self, word: str) -> bool:
        return _normalize(word) in self.common_words

    def confidence_band(self, word: str) -> ConfidenceBand:
        """A: confirmed; B: common but unconfirmed; C: other or rejected.

        Bands describe the evidence policy, not calibrated probabilities.
        """
        normalized = _normalize(word)
        if normalized in self.rejected:
            return "C"
        if normalized in self.confirmed:
            return "A"
        if normalized in self.common_words:
            return "B"
        return "C"

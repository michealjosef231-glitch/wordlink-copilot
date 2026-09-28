"""Deterministic, one-row-per-word recommendations with honest estimate labels."""

from __future__ import annotations

from dataclasses import dataclass

from wordlink.model import FoundWord
from wordlink.solver.scoring import DEFAULT_PROFILE, ScoringProfile, estimate_execution_seconds, proxy_score
from wordlink.vocabulary.policy import VocabularyPolicy

_BAND_PRIORITY = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class RankedWord:
    found: FoundWord
    status: str
    proxy_score: float
    estimated_seconds: float
    utility: float
    confidence_band: str = "C"


def _sort_key(ranked: RankedWord) -> tuple[int, float, float, float, str, tuple[int, ...]]:
    return (
        _BAND_PRIORITY[ranked.confidence_band],
        -ranked.utility,
        -ranked.proxy_score,
        ranked.estimated_seconds,
        ranked.found.word,
        ranked.found.path,
    )


def rank_words(
    found: list[FoundWord],
    policy: VocabularyPolicy | None = None,
    *,
    profile: ScoringProfile = DEFAULT_PROFILE,
) -> list[RankedWord]:
    """Prefer confirmed words, then common words, then other dictionary words.

    Within each band, use proxy per estimated second. A word's best path
    maximizes that same estimated utility; ties are resolved deterministically.
    Common-word and dictionary membership both leave game acceptance unknown.
    """
    best: dict[str, RankedWord] = {}
    for candidate in found:
        status = policy.status(candidate.word) if policy is not None else "unknown"
        if status == "rejected":
            continue
        band = policy.confidence_band(candidate.word) if policy is not None else "C"
        score = proxy_score(candidate)
        seconds = estimate_execution_seconds(candidate, profile)
        ranked = RankedWord(candidate, status, score, seconds, score / seconds, band)
        previous = best.get(candidate.word)
        if previous is None or _sort_key(ranked) < _sort_key(previous):
            best[candidate.word] = ranked
    return sorted(best.values(), key=_sort_key)

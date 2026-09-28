"""Uncalibrated ranking proxy and gesture-duration estimates.

These values are neither observed game points nor measured human execution
times. Their only purpose is a transparent initial ordering of recommendations.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from wordlink.model import FoundWord

PROXY_FORMULA = "dot_sum * word_length"


@dataclass(frozen=True)
class ScoringProfile:
    start_seconds: float = 0.20
    seconds_per_tile: float = 0.12
    seconds_per_turn: float = 0.04
    calibrated: bool = False

    def __post_init__(self) -> None:
        if self.calibrated is not False:
            raise ValueError("This proxy profile has not been calibrated to game scoring")
        for value in (self.start_seconds, self.seconds_per_tile, self.seconds_per_turn):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Gesture estimate coefficients must be finite nonnegative numbers")
        if self.seconds_per_tile <= 0:
            raise ValueError("Seconds per tile must be positive")

    @classmethod
    def from_file(cls, path: Path) -> ScoringProfile:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported scoring profile")
        if data.get("calibrated") is not False or data.get("proxy_formula") != PROXY_FORMULA:
            raise ValueError("Only the explicitly uncalibrated dot-length proxy is supported")
        estimate = data.get("execution_estimate")
        if not isinstance(estimate, dict):
            raise ValueError("Scoring profile is missing its gesture estimate")
        return cls(
            start_seconds=estimate.get("start_seconds"),
            seconds_per_tile=estimate.get("seconds_per_tile"),
            seconds_per_turn=estimate.get("seconds_per_turn"),
        )


DEFAULT_PROFILE = ScoringProfile()


def count_turns(path: tuple[int, ...]) -> int:
    directions = tuple(
        (second // 4 - first // 4, second % 4 - first % 4)
        for first, second in zip(path, path[1:])
    )
    return sum(first != second for first, second in zip(directions, directions[1:]))


def proxy_score(found: FoundWord) -> float:
    return float(found.dot_sum * len(found.word))


def estimate_execution_seconds(found: FoundWord, profile: ScoringProfile = DEFAULT_PROFILE) -> float:
    return (
        profile.start_seconds
        + profile.seconds_per_tile * len(found.path)
        + profile.seconds_per_turn * count_turns(found.path)
    )

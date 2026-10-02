from __future__ import annotations

from dataclasses import dataclass

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Board:
    letters: tuple[str, ...]
    dots: tuple[int, ...]
    boxes: tuple[Box, ...] = ()

    def __post_init__(self) -> None:
        if len(self.letters) != 16 or len(self.dots) != 16:
            raise ValueError("A board requires exactly 16 tile tokens and 16 dot values")
        if any(letter != "QU" and (len(letter) != 1 or not ("A" <= letter <= "Z")) for letter in self.letters):
            raise ValueError("Board letters must be uppercase A-Z or QU")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10 for value in self.dots):
            raise ValueError("Dot values must be integers from 0 to 10")
        if self.boxes and (len(self.boxes) != 16 or any(len(box) != 4 or box[2] <= 0 or box[3] <= 0 for box in self.boxes)):
            raise ValueError("Board boxes must contain 16 positive tile rectangles")


@dataclass(frozen=True)
class FoundWord:
    word: str
    path: tuple[int, ...]
    dot_sum: int


@dataclass(frozen=True)
class TilePrediction:
    letter: str
    dots: int
    confidence: float
    box: Box


@dataclass(frozen=True)
class Recognition:
    board: Board
    tiles: tuple[TilePrediction, ...]
    elapsed_ms: float
    warnings: tuple[str, ...] = ()

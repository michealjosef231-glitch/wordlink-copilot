"""Screenshot-to-Board recognition with per-tile uncertainty retained."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from wordlink.model import Board, Box, Recognition, TilePrediction
from wordlink.vision.dots import count_dots
from wordlink.vision.letters import recognize_letter
from wordlink.vision.tiles import detect_tiles


def _read_tiles(source: np.ndarray, boxes: tuple[Box, ...], turns: int, template_dir: Path | None):
    readings = []
    for x, y, width, height in boxes:
        crop = np.ascontiguousarray(np.rot90(source[y:y + height, x:x + width], turns))
        letter, shape_score, margin = recognize_letter(crop, template_dir)
        dots, dot_score = count_dots(crop)
        readings.append((letter, shape_score, margin, dots, dot_score))
    return readings


def recognize(image: np.ndarray | Path, template_dir: Path | None = None) -> Recognition:
    """Read sixteen row-major letters and dot counts from a BGR image or path.

    Boxes and predictions remain row-major in source-image coordinates, even
    when glyphs need rotation for reading. Confidence is a glyph/dot shape score.
    It does not represent a measured
    probability that the prediction is correct. Warnings identify weak matches.
    """
    started = perf_counter()
    if isinstance(image, (Path, str)):
        source = cv2.imread(str(image), cv2.IMREAD_COLOR)
        if source is None:
            raise ValueError(f"Cannot read screenshot: {image}")
    else:
        source = np.asarray(image)
    if source.ndim != 3 or source.shape[2] != 3 or source.dtype != np.uint8 or min(source.shape[:2]) < 40:
        raise ValueError("Expected a nonempty uint8 BGR screenshot with three channels")
    boxes = detect_tiles(source)
    readings = _read_tiles(source, boxes, 0, template_dir)
    # Strong upright reads need no extra work. Poor reads and displaced/missing
    # dot rows trigger the four orientations. Rectangles stay source row-major.
    if any(shape < .82 or dots == 0 or dot_shape < .65 for _, shape, _, dots, dot_shape in readings):
        candidates = [(0, readings)]
        for angle in (1, 2, 3):
            try:
                candidates.append((angle, _read_tiles(source, boxes, angle, template_dir)))
            except ValueError:
                continue
        _, readings = max(candidates, key=lambda entry: np.mean([
            .9 * shape + .1 * dot_shape for _, shape, _, _, dot_shape in entry[1]
        ]))
    predictions: list[TilePrediction] = []
    warnings: list[str] = []
    for index, (box, reading) in enumerate(zip(boxes, readings)):
        letter, shape_score, margin, dots, dot_score = reading
        confidence = min(shape_score, dot_score)
        predictions.append(TilePrediction(letter, dots, confidence, box))
        if shape_score < .82 or margin < .035:
            warnings.append(f"Tile {index + 1}: uncertain letter {letter} (shape {shape_score:.3f}, margin {margin:.3f})")
        if dot_score < .65:
            warnings.append(f"Tile {index + 1}: uncertain dot count {dots} (shape {dot_score:.3f})")
    board = Board(tuple(p.letter for p in predictions), tuple(p.dots for p in predictions), boxes)
    return Recognition(board, tuple(predictions), (perf_counter() - started) * 1000, tuple(warnings))

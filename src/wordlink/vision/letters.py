"""Small, inspectable glyph-template matcher; no OCR service or model required."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import cv2
import numpy as np

DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "data" / "templates"
GLYPH_SIZE = 64


def normalize_glyph(mask: np.ndarray, size: int = GLYPH_SIZE) -> np.ndarray:
    """Crop a foreground mask and center it without changing its aspect ratio."""
    points = cv2.findNonZero((mask > 0).astype(np.uint8))
    if points is None:
        raise ValueError("No letter pixels found in tile")
    x, y, width, height = cv2.boundingRect(points)
    glyph = mask[y : y + height, x : x + width]
    scale = (size - 8) / max(width, height)
    resized = cv2.resize(
        glyph, (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    result = np.zeros((size, size), dtype=np.uint8)
    top = (size - resized.shape[0]) // 2
    left = (size - resized.shape[1]) // 2
    result[top : top + resized.shape[0], left : left + resized.shape[1]] = resized
    return (result > 127).astype(np.uint8) * 255


def extract_glyph(tile: np.ndarray) -> np.ndarray:
    """Separate the central dark letter from the tile edge and bottom dots."""
    height, width = tile.shape[:2]
    if min(height, width) < 12:
        raise ValueError("Tile is too small to read")
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    region = gray[round(height * 0.12) : round(height * 0.73),
                  round(width * 0.12) : round(width * 0.88)]
    dark = (region < 115).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark)
    components = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= max(3, width * height * .003)]
    if not components:
        raise ValueError("No readable letter found in tile")
    # Qu has two substantial disconnected components. Dropping the smaller
    # one turns its Q into an apparently confident O and creates illegal paths.
    return normalize_glyph(np.isin(labels, components).astype(np.uint8) * 255)


@lru_cache(maxsize=8)
def load_templates(template_dir: str) -> tuple[tuple[str, np.ndarray], ...]:
    directory = Path(template_dir)
    templates: list[tuple[str, np.ndarray]] = []
    packed = directory / "glyphs.npz"
    if packed.is_file():
        try:
            with np.load(packed, allow_pickle=False) as archive:
                tokens, masks = archive["tokens"], archive["masks"]
            valid = (tokens.ndim == 1 and masks.shape == (len(tokens), GLYPH_SIZE, GLYPH_SIZE)
                     and masks.dtype == np.uint8 and len(tokens) > 0
                     and all(re.fullmatch(r"QU|[A-Z]", str(token)) for token in tokens)
                     and set("ABCDEFGHIJKLMNOPQRSTUVWXYZ").issubset(set(tokens))
                     and all(np.any(mask) for mask in masks))
            if valid:
                return tuple((str(token), mask) for token, mask in zip(tokens, masks))
        except (OSError, ValueError, KeyError):
            pass  # Original PNG templates remain a validated recovery route.
    for path in sorted(directory.glob("*.png")):
        if not re.fullmatch(r"(?:QU|[A-Z])(?:[-_.].*)?", path.stem):
            continue
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Unreadable letter template: {path.name}")
        templates.append((path.stem.split("-")[0].split("_")[0].split(".")[0], normalize_glyph(image)))
    missing = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") - {letter for letter, _ in templates}
    if missing:
        raise ValueError(f"Missing letter templates in {directory}: {''.join(sorted(missing))}")
    return tuple(templates)


@lru_cache(maxsize=8)
def _template_matrix(template_dir: str) -> tuple[tuple[str, ...], np.ndarray, np.ndarray, np.ndarray]:
    templates = load_templates(template_dir)
    matrix = np.stack([(mask > 127).ravel() for _, mask in templates])
    distances = np.stack([
        cv2.distanceTransform((mask <= 127).astype(np.uint8), cv2.DIST_L2, 5).ravel()
        for _, mask in templates
    ])
    return tuple(letter for letter, _ in templates), matrix, np.count_nonzero(matrix, axis=1), distances


def match_glyph(glyph: np.ndarray, template_dir: Path | None = None) -> tuple[str, float, float]:
    """Return the best letter, shape score, and margin over a different letter.

    Scores measure template similarity, not calibrated recognition probability.
    """
    letters, matrix, template_areas, distances = _template_matrix(str((template_dir or DEFAULT_TEMPLATE_DIR).resolve()))
    target = (glyph > 127).ravel()
    target_sum = int(np.count_nonzero(target))
    intersections = np.count_nonzero(matrix & target, axis=1)
    dice = 2 * intersections / (target_sum + template_areas)
    target_distances = cv2.distanceTransform((glyph <= 127).astype(np.uint8), cv2.DIST_L2, 5).ravel()
    # Symmetric stroke distance distinguishes shared outlines with different
    # interior strokes (G/O, E/F) and tolerates small antialiasing differences.
    candidate_to_target = np.einsum("ij,j->i", matrix, target_distances) / template_areas
    target_to_candidate = np.einsum("ij,j->i", distances, target) / target_sum
    chamfer = (candidate_to_target + target_to_candidate) / 2
    similarities = .6 * dice + .4 * np.exp(-chamfer / 2)
    scores: dict[str, float] = {}
    for letter, score in zip(letters, similarities):
        scores[letter] = max(float(score), scores.get(letter, 0.0))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[0][0], ranked[0][1], ranked[0][1] - ranked[1][1]


def recognize_letter(tile: np.ndarray, template_dir: Path | None = None) -> tuple[str, float, float]:
    return match_glyph(extract_glyph(tile), template_dir)

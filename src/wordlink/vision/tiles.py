"""Locate a regular 4x4 arrangement of light square tiles on a blue board."""

from __future__ import annotations

from itertools import product

import cv2
import numpy as np

from wordlink.model import Box


def _overlap(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    area = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return area / min(aw * ah, bw * bh)


def _candidates(image: np.ndarray) -> list[Box]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    side = min(image.shape[:2])
    candidates: list[Box] = []
    for brightness in (155, 185, 210, 230):
        mask = ((hsv[:, :, 2] > brightness) & (hsv[:, :, 1] < 110)).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            if not (max(12, side * .035) <= min(width, height) <= side * .3):
                continue
            if not .78 <= width / height <= 1.28:
                continue
            if cv2.contourArea(contour) / (width * height) < .70:
                continue
            box = (x, y, width, height)
            if not any(_overlap(box, old) > .82 for old in candidates):
                candidates.append(box)
    return candidates


def _rows(boxes: list[Box], height: float) -> list[list[Box]]:
    rows: list[list[Box]] = []
    for box in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        center = box[1] + box[3] / 2
        if rows and abs(center - np.mean([b[1] + b[3] / 2 for b in rows[-1]])) < height * .25:
            rows[-1].append(box)
        else:
            rows.append([box])
    return [sorted(row, key=lambda b: b[0]) for row in rows]


def _blue_fraction(image: np.ndarray, boxes: tuple[Box, ...]) -> float:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    crop = image[y0:y1, x0:x1]
    gaps = np.ones(crop.shape[:2], dtype=bool)
    for x, y, width, height in boxes:
        gaps[y - y0 : y - y0 + height, x - x0 : x - x0 + width] = False
    if not gaps.any():
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue = (hsv[:, :, 0] >= 90) & (hsv[:, :, 0] <= 140) & (hsv[:, :, 1] > 65)
    return float(blue[gaps].mean())


def detect_tiles(image: np.ndarray) -> tuple[Box, ...]:
    """Return sixteen original-image rectangles in row-major order.

    Positions come from tile contours and grid regularity, never fixture names or
    fixed screenshot coordinates. A screenshot without a complete grid is rejected.
    """
    candidates = _candidates(image)
    best: tuple[Box, ...] | None = None
    best_quality = 0.0
    blue_fractions: dict[tuple[Box, ...], float] = {}
    for base in candidates:
        width, height = base[2:]
        # The recording visibly shrinks recently selected tiles during feedback.
        # Their centers still form the same grid, so accept moderate size changes.
        similar = [b for b in candidates if .74 <= b[2] / width <= 1.36 and .74 <= b[3] / height <= 1.36]
        rows = [row for row in _rows(similar, height) if len(row) >= 4]
        for start in range(len(rows) - 3):
            selected = rows[start : start + 4]
            row_options = [[row[i:i + 4] for i in range(len(row) - 3)] for row in selected]
            # Limit pathological images with hundreds of square decorations.
            if np.prod([len(options) for options in row_options]) > 1000:
                continue
            for arrangement in product(*row_options):
                centers = np.array([[[b[0] + b[2] / 2, b[1] + b[3] / 2] for b in row] for row in arrangement])
                xs = centers[:, :, 0]
                ys = centers[:, :, 1]
                horizontal = np.diff(xs, axis=1)
                vertical = np.diff(ys.mean(axis=1))
                if not (np.all((horizontal > width * .95) & (horizontal < width * 1.8))
                        and np.all((vertical > height * .95) & (vertical < height * 1.8))):
                    continue
                if xs.std(axis=0).max() > width * .10 or ys.std(axis=1).max() > height * .10:
                    continue
                if horizontal.std() > width * .10 or vertical.std() > height * .10:
                    continue
                boxes = tuple(b for row in arrangement for b in row)
                # Different base tiles often generate the same grid. Its blue
                # pixels cannot change within this call, so inspect them once.
                # Keep the base-dependent geometry and quality calculations:
                # varying tile sizes can change eligibility and tie ordering.
                if boxes not in blue_fractions:
                    blue_fractions[boxes] = _blue_fraction(image, boxes)
                blue_fraction = blue_fractions[boxes]
                if blue_fraction < .18:
                    continue
                quality = blue_fraction - float(horizontal.std() + vertical.std()) / (width + height)
                if quality > best_quality:
                    best, best_quality = boxes, quality
    if best is None:
        raise ValueError("No complete 4x4 light-tile board found on a blue background")
    return best

"""Count small dark dot components below the central tile letter."""

from __future__ import annotations

import cv2
import numpy as np


def count_dots(tile: np.ndarray) -> tuple[int, float]:
    """Return the count and a shape-quality score, not calibrated probability."""
    height, width = tile.shape[:2]
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    bottom = gray[round(height * .72) : round(height * .95), round(width * .12) : round(width * .88)]
    dark = (bottom < 130).astype(np.uint8) * 255
    count, _, stats, _ = cv2.connectedComponentsWithStats(dark)
    sizes: list[int] = []
    uncertain = False
    for i in range(1, count):
        _, _, w, h, area = stats[i]
        if area < max(2, width * height * .0007):
            continue
        if (.45 <= w / h <= 2.1 and max(w, h) <= width * .16
                and area <= width * height * .018):
            sizes.append(int(area))
        else:
            uncertain = True
    if len(sizes) > 10:
        raise ValueError("Too many dark components to identify tile dots")
    uniformity = 1.0 if len(sizes) < 2 else min(sizes) / max(sizes)
    return len(sizes), min(uniformity, .45 if uncertain else 1.0)

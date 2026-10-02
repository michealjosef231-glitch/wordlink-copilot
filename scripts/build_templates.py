"""Generate local A-Z and Qu bitmap templates from installed fonts, without font copies.

Run from the project root: .venv/bin/python scripts/build_templates.py
These are synthetic training glyphs, not labels from evaluation screenshots.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wordlink.vision.letters import normalize_glyph


def build(output: Path, fonts: list[Path]) -> int:
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    for path in fonts:
        if not path.is_file():
            raise FileNotFoundError(path)
        for weight in (500, 600, 700, 800):
            font = ImageFont.truetype(str(path), 100)
            try:
                axes = font.get_variation_axes()
            except OSError:
                axes = []
            if not axes and weight != 700:
                continue
            if axes:
                values = [axis["default"] for axis in axes]
                for i, axis in enumerate(axes):
                    if b"Weight" in axis["name"]:
                        values[i] = min(axis["maximum"], max(axis["minimum"], weight))
                font.set_variation_by_axes(values)
            for letter in (*"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "Qu"):
                canvas = Image.new("L", (180, 180), 0)
                draw = ImageDraw.Draw(canvas)
                draw.text((30, 10), letter, font=font, fill=255)
                mask = normalize_glyph(np.asarray(canvas))
                name = f"{letter.upper()}-{path.stem}-{weight}.png"
                if not cv2.imwrite(str(output / name), mask):
                    raise OSError(f"Could not write {name}")
                total += 1
    paths = sorted(output.glob("*.png"))
    tokens = [path.stem.split("-")[0] for path in paths]
    masks = np.stack([normalize_glyph(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)) for path in paths])
    np.savez_compressed(output / "glyphs.npz", tokens=np.array(tokens), masks=masks)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/templates"))
    parser.add_argument("--font", type=Path, action="append")
    args = parser.parse_args()
    fonts = args.font or [
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/System/Library/Fonts/SFCompact.ttf"),
        Path("/System/Library/Fonts/SFNSRounded.ttf"),
        Path("/System/Library/Fonts/SFCompactRounded.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"),
    ]
    print(f"Generated {build(args.output, fonts)} templates in {args.output}")

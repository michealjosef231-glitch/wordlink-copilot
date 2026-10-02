from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from wordlink.vision.board import recognize
from wordlink.vision.dots import count_dots
from wordlink.vision.letters import load_templates, normalize_glyph
from wordlink.vision.tiles import detect_tiles

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "boards"
LABELS = json.loads((FIXTURE_DIR / "labels.json").read_text())["boards"]


@pytest.mark.parametrize("label", LABELS, ids=[label["file"] for label in LABELS])
def test_independently_labeled_recording_boards(label):
    result = recognize(FIXTURE_DIR / label["file"])
    assert result.board.letters == tuple("".join(label["letters"]))
    assert result.board.dots == tuple(dot for row in label["dots"] for dot in row)
    assert len(result.tiles) == 16
    assert result.warnings == ()


@pytest.mark.parametrize("turns", [1, 2, 3])
def test_rotated_recording_keeps_source_row_major_boxes(turns):
    label = LABELS[0]
    original = cv2.imread(str(FIXTURE_DIR / label["file"]))
    image = np.ascontiguousarray(np.rot90(original, turns))
    result = recognize(image)
    letters = np.array([list(row) for row in label["letters"]])
    dots = np.array(label["dots"])
    assert result.board.letters == tuple(np.rot90(letters, turns).ravel())
    assert result.board.dots == tuple(int(dot) for dot in np.rot90(dots, turns).ravel())
    assert all(0 <= x < image.shape[1] and 0 <= y < image.shape[0]
               and x + width <= image.shape[1] and y + height <= image.shape[0]
               for x, y, width, height in result.board.boxes)
    assert result.warnings == ()


@pytest.mark.parametrize("scale", [.75, 1.5])
def test_resized_real_screenshot(scale):
    label = LABELS[0]
    original = cv2.imread(str(FIXTURE_DIR / label["file"]))
    result = recognize(cv2.resize(original, None, fx=scale, fy=scale))
    assert result.board.letters == tuple("".join(label["letters"]))
    assert result.board.dots == tuple(dot for row in label["dots"] for dot in row)


def synthetic_grid(scale: float = 1.0) -> np.ndarray:
    image = np.full((450, 420, 3), (190, 90, 20), np.uint8)
    for row in range(4):
        for col in range(4):
            x, y = 20 + col * 100, 40 + row * 100
            cv2.rectangle(image, (x, y), (x + 79, y + 79), (245, 245, 245), -1)
    return cv2.resize(image, None, fx=scale, fy=scale)


@pytest.mark.parametrize("scale", [.6, 1, 1.4])
def test_grid_detection_scales_and_returns_row_major_boxes(scale):
    boxes = detect_tiles(synthetic_grid(scale))
    assert len(boxes) == 16
    assert all(abs(x - (20 + (index % 4) * 100) * scale) < 3
               and abs(y - (40 + (index // 4) * 100) * scale) < 3
               for index, (x, y, _, _) in enumerate(boxes))


def test_missing_or_incomplete_board_is_rejected():
    with pytest.raises(ValueError, match="4x4"):
        detect_tiles(np.full((300, 300, 3), 255, np.uint8))
    image = synthetic_grid()
    image[40:120, 20:100] = (190, 90, 20)
    with pytest.raises(ValueError, match="4x4"):
        detect_tiles(image)


def test_same_tile_geometry_requires_blue_background_in_each_frame():
    image = synthetic_grid()
    boxes = detect_tiles(image)
    assert len(boxes) == 16
    # Identical tile contours in a later non-game screen are insufficient.
    changed = image.copy()
    background = np.all(changed == (190, 90, 20), axis=2)
    changed[background] = (20, 30, 190)
    with pytest.raises(ValueError, match="4x4"):
        detect_tiles(changed)
    assert detect_tiles(image) == boxes


@pytest.mark.parametrize("dots", range(6))
def test_dot_count_ignores_letter_and_tile_edges(dots):
    tile = np.full((90, 90, 3), 245, np.uint8)
    cv2.putText(tile, "M", (22, 53), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (25, 25, 25), 3)
    for index in range(dots):
        cv2.circle(tile, (45 + (2 * index - dots + 1) * 5, 75), 3, (40, 40, 40), -1)
    actual, quality = count_dots(tile)
    assert actual == dots
    assert quality > .8


def test_glyph_normalization_preserves_aspect_ratio():
    mask = np.zeros((80, 90), np.uint8)
    mask[10:70, 30:42] = 255
    normalized = normalize_glyph(mask)
    ys, xs = np.nonzero(normalized)
    assert .15 < (xs.max() - xs.min()) / (ys.max() - ys.min()) < .25
    with pytest.raises(ValueError, match="No letter"):
        normalize_glyph(np.zeros((30, 30), np.uint8))


def test_incomplete_custom_alphabet_is_rejected(tmp_path):
    cv2.imwrite(str(tmp_path / "A.png"), np.eye(30, dtype=np.uint8) * 255)
    with pytest.raises(ValueError, match="Missing letter templates"):
        load_templates(str(tmp_path))


def test_bad_image_inputs_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Cannot read screenshot"):
        recognize(tmp_path / "missing.png")
    with pytest.raises(ValueError, match="BGR"):
        recognize(np.zeros((100, 100), np.uint8))

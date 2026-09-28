from pathlib import Path

import cv2
import numpy as np

from wordlink.model import Board, FoundWord


def draw_overlay(image: np.ndarray, board: Board, found: FoundWord) -> np.ndarray:
    if not board.boxes:
        raise ValueError("An image overlay requires detected tile boxes")
    banner_height = 52
    result = np.full((image.shape[0] + banner_height, image.shape[1], 3), (23, 28, 37), dtype=np.uint8)
    result[banner_height:] = image
    centers = [(int(x + w / 2), int(y + h / 2) + banner_height) for x, y, w, h in board.boxes]
    for first, second in zip(found.path, found.path[1:]):
        cv2.line(result, centers[first], centers[second], (25, 220, 255), 6, cv2.LINE_AA)
    for step, index in enumerate(found.path, 1):
        x, y, width, height = board.boxes[index]
        point = (int(x + width * 0.2), int(y + height * 0.2) + banner_height)
        color = (75, 210, 110) if step == 1 else ((80, 90, 240) if step == len(found.path) else (25, 220, 255))
        cv2.circle(result, point, 12, (20, 25, 30), -1, cv2.LINE_AA)
        cv2.circle(result, point, 12, color, 2, cv2.LINE_AA)
        size = cv2.getTextSize(str(step), cv2.FONT_HERSHEY_SIMPLEX, .4, 1)[0]
        cv2.putText(result, str(step), (point[0] - size[0] // 2, point[1] + size[1] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1, cv2.LINE_AA)
    title = f"{found.word}  |  {len(found.path)} tiles  |  dictionary candidate"
    title_width = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, .55, 1)[0][0]
    scale = .55 * min(1.0, (result.shape[1] - 20) / title_width)
    cv2.putText(result, title, (10, 31), cv2.FONT_HERSHEY_SIMPLEX, scale, (240, 240, 240), 1, cv2.LINE_AA)
    return result


def save_overlay(path: Path, image: np.ndarray, board: Board, found: FoundWord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), draw_overlay(image, board, found)):
        raise ValueError(f"Cannot save overlay: {path}")

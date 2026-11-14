from __future__ import annotations

import cv2
import numpy as np


def enlarge_crop(jpeg: bytes, bbox: tuple[float, float, float, float], scale: float = 2.0) -> bytes:
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("frame is not a jpeg")
    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("flame box is outside the frame")
    crop = image[int(y1) : int(y2), int(x1) : int(x2)]
    if crop.size == 0:
        raise ValueError("flame crop is empty")
    enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    ok, encoded = cv2.imencode(".jpg", enlarged)
    if not ok:
        raise ValueError("crop encode failed")
    return encoded.tobytes()

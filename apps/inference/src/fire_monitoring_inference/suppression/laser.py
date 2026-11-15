from __future__ import annotations

import cv2
import numpy as np

from ..multiview_geometry import triangulate


def detect_red_dot(frame, previous, *, sat_min: int = 80, diff_min: int = 25) -> tuple[float, float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = ((hue <= 10) | (hue >= 170)) & (saturation >= sat_min) & (value >= 40)
    changed = cv2.absdiff(frame, previous).max(axis=2) >= diff_min
    ys, xs = np.nonzero(red & changed)
    if len(xs) < 3:
        raise RuntimeError("red dot not found")
    return float(xs.mean()), float(ys.mean())


def triangulate_dot(pixels, intrinsics, distortion, poses) -> np.ndarray:
    point, rank = triangulate(
        np.asarray(pixels, dtype=float),
        np.asarray(intrinsics, dtype=float),
        distortion,
        np.asarray(poses, dtype=float),
    )
    if rank < 3:
        raise RuntimeError("laser point is not observable")
    return point

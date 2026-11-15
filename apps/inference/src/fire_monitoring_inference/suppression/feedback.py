from __future__ import annotations

import numpy as np


def corrected_aim(target, landing) -> np.ndarray:
    target = np.asarray(target, dtype=float)
    landing = np.asarray(landing, dtype=float)
    return target - (landing - target)


def zigzag(mean, covariance, radius: float) -> list[np.ndarray]:
    mean = np.asarray(mean, dtype=float)
    horizontal = np.asarray(covariance, dtype=float)[:2, :2]
    values, vectors = np.linalg.eigh(horizontal)
    major = int(np.argmax(values))
    minor = 1 - major
    sigma = float(np.sqrt(max(float(values[major]), 0.0)))
    step = max(float(radius), 0.05)
    count = max(1, int(np.ceil((2 * sigma) / step)))
    points = []
    for index in range(-count, count + 1):
        side = 0.0 if index == 0 else (1.0 if index % 2 else -1.0) * 0.5 * step
        xy = mean[:2] + index * step * vectors[:, major] + side * vectors[:, minor]
        points.append(np.array([xy[0], xy[1], float(mean[2])]))
    return points

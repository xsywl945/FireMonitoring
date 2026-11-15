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


ELLIPSE_K = 2.0


def _axis_count(half: float, step: float) -> int:
    if 2 * half <= step:
        return 1
    return int(np.ceil((2 * half) / step))


def _from_center(values: np.ndarray) -> list[float]:
    middle = len(values) // 2
    order = [middle]
    for step in range(1, len(values)):
        if middle - step >= 0:
            order.append(middle - step)
        if middle + step < len(values):
            order.append(middle + step)
    return [float(values[index]) for index in order]


def ellipse_sweep(mean, covariance, radius: float, *, k: float = ELLIPSE_K, max_points: int | None = None) -> list[np.ndarray]:
    if radius <= 0:
        raise ValueError("sweep radius must be positive")
    if k <= 0:
        raise ValueError("ellipse scale must be positive")
    mean = np.asarray(mean, dtype=float).reshape(3)
    plane = np.asarray(covariance, dtype=float)[:2, :2]
    plane = 0.5 * (plane + plane.T)
    values, vectors = np.linalg.eigh(plane)
    values = np.maximum(values, 0.0)
    step = float(radius)
    halves = [k * float(np.sqrt(value)) for value in values]
    counts = [_axis_count(half, step) for half in halves]
    if max_points is not None and counts[0] * counts[1] > max_points:
        return []
    axes = []
    for count, half in zip(counts, halves, strict=True):
        samples = np.array([0.0]) if count == 1 else np.linspace(-half, half, count)
        axes.append(_from_center(samples))
    points = []
    for row_index, along in enumerate(axes[0]):
        across = axes[1] if row_index % 2 == 0 else list(reversed(axes[1]))
        for side in across:
            xy = mean[:2] + along * vectors[:, 0] + side * vectors[:, 1]
            points.append(np.array([xy[0], xy[1], float(mean[2])]))
    return points


def plan_spray(mean, covariance, radius: float, *, max_points: int, threshold: float) -> dict:
    if max_points < 1:
        raise ValueError("water budget needs at least one point")
    points = ellipse_sweep(mean, covariance, radius, max_points=max_points)
    if not points:
        return {"spray": False, "points": [], "nominal": 0.0}
    from .coverage import pattern_cover_probability

    offsets = np.stack(points) - np.asarray(mean, dtype=float).reshape(3)
    nominal = pattern_cover_probability(covariance, offsets, radius)
    if nominal < threshold:
        return {"spray": False, "points": [], "nominal": nominal}
    return {"spray": True, "points": points, "nominal": nominal}

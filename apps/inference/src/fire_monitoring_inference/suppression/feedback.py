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


def _landing_offsets(covariance, radius: float, max_points: int) -> list[np.ndarray]:
    plane = np.asarray(covariance, dtype=float)[:2, :2]
    plane = 0.5 * (plane + plane.T)
    values, vectors = np.linalg.eigh(plane)
    major = int(np.argmax(values))
    axes = [major, 1 - major]
    offsets = [np.zeros(3)]
    ring = 1
    while len(offsets) < max_points:
        for axis in axes:
            direction = vectors[:, axis]
            for sign in (1.0, -1.0):
                xy = sign * ring * radius * direction
                offsets.append(np.array([xy[0], xy[1], 0.0]))
                if len(offsets) >= max_points:
                    return offsets
        ring += 1
    return offsets


def plan_path(mean, covariance, radius: float, *, max_points: int) -> dict:
    if radius <= 0:
        raise ValueError("sweep radius must be positive")
    if max_points < 1:
        raise ValueError("water budget needs at least one point")
    from .coverage import prefix_cover_probabilities

    mean = np.asarray(mean, dtype=float).reshape(3)
    offsets = _landing_offsets(covariance, radius, max_points)
    probabilities = prefix_cover_probabilities(covariance, offsets, radius)
    best_n = 1
    best_p = probabilities[0]
    for count, probability in enumerate(probabilities, start=1):
        if probability > best_p:
            best_p = probability
            best_n = count
    points = [mean + offsets[index] for index in range(best_n)]
    return {"points": points, "nominal": best_p}


def plan_spray(mean, covariance, radius: float, *, max_points: int, threshold: float) -> dict:
    planned = plan_path(mean, covariance, radius, max_points=max_points)
    return {
        "spray": planned["nominal"] >= threshold,
        "points": planned["points"] if planned["nominal"] >= threshold else [],
        "nominal": planned["nominal"],
    }

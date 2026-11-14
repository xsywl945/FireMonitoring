from __future__ import annotations

import math

import numpy as np


def _edges(polygon: list[tuple[float, float]]):
    return list(zip(polygon, polygon[1:] + polygon[:1], strict=True))


def _cross(origin, left, right) -> float:
    return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (
        right[0] - origin[0]
    )


def _segments_intersect(a, b, c, d) -> bool:
    ab_c = _cross(a, b, c)
    ab_d = _cross(a, b, d)
    cd_a = _cross(c, d, a)
    cd_b = _cross(c, d, b)
    if ab_c == 0 and ab_d == 0:
        return False
    return ab_c * ab_d <= 0 and cd_a * cd_b <= 0


def _point_in_polygon(point, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    x, y = point
    for start, end in _edges(polygon):
        if (start[1] > y) == (end[1] > y):
            continue
        cross_x = (end[0] - start[0]) * (y - start[1]) / (end[1] - start[1]) + start[0]
        if x < cross_x:
            inside = not inside
    return inside


def hits_region(subject: list[tuple[float, float]], region: list[tuple[float, float]]) -> bool:
    if len(region) < 3:
        raise ValueError("combustible region needs three points")
    if len(subject) == 2:
        if _point_in_polygon(subject[0], region) or _point_in_polygon(subject[1], region):
            return True
        return any(_segments_intersect(subject[0], subject[1], *edge) for edge in _edges(region))
    if len(subject) < 3:
        raise ValueError("spread footprint is empty")
    if any(_point_in_polygon(point, region) for point in subject):
        return True
    if any(_point_in_polygon(point, subject) for point in region):
        return True
    return any(
        _segments_intersect(*left, *right)
        for left in _edges(subject)
        for right in _edges(region)
    )


def _velocity(times: np.ndarray, points: np.ndarray) -> tuple[float, float]:
    if times[-1] == times[0]:
        return 0.0, 0.0
    vx = float(np.polyfit(times, points[:, 0], 1)[0])
    vy = float(np.polyfit(times, points[:, 1], 1)[0])
    return vx, vy


def _move(point: tuple[float, float], velocity: tuple[float, float], seconds: float):
    return (point[0] + velocity[0] * seconds, point[1] + velocity[1] * seconds)


def analyze_spread(tracks: list[dict], regions: list[dict]) -> dict:
    if not tracks:
        raise ValueError("spread needs a footprint")
    ordered = sorted(tracks, key=lambda item: item["t"])
    times = np.array([item["t"] for item in ordered], dtype=float)
    left = np.array([item["left"] for item in ordered], dtype=float)
    right = np.array([item["right"] for item in ordered], dtype=float)
    left_v = _velocity(times, left)
    right_v = _velocity(times, right)
    current_left = (float(left[-1, 0]), float(left[-1, 1]))
    current_right = (float(right[-1, 0]), float(right[-1, 1]))
    centroid = (
        (current_left[0] + current_right[0]) / 2,
        (current_left[1] + current_right[1]) / 2,
    )
    centroid_v = ((left_v[0] + right_v[0]) / 2, (left_v[1] + right_v[1]) / 2)
    speed = math.hypot(*centroid_v)
    direction = math.degrees(math.atan2(centroid_v[1], centroid_v[0])) if speed else 0.0

    def horizon(seconds: float) -> list[list[float]]:
        future_left = _move(current_left, left_v, seconds)
        future_right = _move(current_right, right_v, seconds)
        return [
            list(current_left),
            list(current_right),
            list(future_right),
            list(future_left),
        ]

    now = [list(current_left), list(current_right)]
    polygons = {0: now, 30: horizon(30), 60: horizon(60)}
    hits = []
    for region in regions:
        polygon = [tuple(point) for point in region["polygon"]]
        for seconds, shape in polygons.items():
            subject = [tuple(point) for point in shape]
            if hits_region(subject, polygon):
                hits.append({"name": region["name"], "horizon_s": seconds})
    return {
        "status": "ESTIMATED",
        "left_m": list(current_left),
        "right_m": list(current_right),
        "centroid_m": [centroid[0], centroid[1]],
        "speed_m_s": speed,
        "direction_deg": direction,
        "now": now,
        "horizon_30s": polygons[30],
        "horizon_60s": polygons[60],
        "hits": hits,
    }

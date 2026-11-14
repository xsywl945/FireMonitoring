from __future__ import annotations

import numpy as np

from .size import camera_depth, heat_release_kw


def _box_size(sample: dict) -> tuple[float, float, float]:
    x1, y1, x2, y2 = sample["bbox"]
    width = x2 - x1
    height = y2 - y1
    return width, height, width * height


def measurements(
    *,
    position: dict | None,
    samples: list[dict],
    calibrations: dict,
    sigma: float,
) -> dict:
    area = []
    for sample in samples:
        _width, _height, box_area = _box_size(sample)
        if box_area <= 0:
            raise ValueError("flame box must be positive")
        area.append((sample["t"], box_area))
    estimated = position is not None and position.get("status") == "ESTIMATED"
    if not estimated or not samples:
        return {"views": [], "heat_samples": [], "area_samples": area}
    world = position["xyz"]
    depth = {
        camera_id: camera_depth(world, calibration, sigma)
        for camera_id, calibration in calibrations.items()
    }
    heat = []
    latest: dict[int, dict] = {}
    for sample in sorted(samples, key=lambda item: item["t"]):
        camera_id = sample["camera_id"]
        if camera_id not in depth or camera_id not in calibrations:
            continue
        calibration = calibrations[camera_id]
        fx = calibration["intrinsics"][0][0]
        fy = calibration["intrinsics"][1][1]
        width, height, _area = _box_size(sample)
        z = depth[camera_id]
        heat.append((sample["t"], heat_release_kw(height * z / fy, width * z / fx)))
        latest[camera_id] = {
            "h_px": height,
            "w_px": width,
            "z_m": z,
            "fx": fx,
            "fy": fy,
        }
    return {"views": list(latest.values()), "heat_samples": _bucket(heat), "area_samples": area}


def _bucket(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not samples:
        return []
    grouped: dict[int, list[tuple[float, float]]] = {}
    for moment, value in samples:
        grouped.setdefault(round(moment * 2), []).append((moment, value))
    reduced = []
    for key in sorted(grouped):
        chunk = grouped[key]
        reduced.append((chunk[-1][0], float(np.median([item[1] for item in chunk]))))
    return reduced

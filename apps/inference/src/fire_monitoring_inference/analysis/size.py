from __future__ import annotations

import math

import numpy as np


def heat_release_kw(height_m: float, diameter_m: float) -> float:
    if height_m <= 0 or diameter_m <= 0:
        raise ValueError("flame size must be positive")
    base = height_m + 1.02 * diameter_m
    if base <= 0:
        raise ValueError("Heskestad correlation is not positive")
    return float((base / 0.235) ** 2.5)


def flame_length_m(heat_release_kw_value: float, diameter_m: float) -> float:
    if heat_release_kw_value <= 0 or diameter_m <= 0:
        raise ValueError("heat release and diameter must be positive")
    return 0.235 * heat_release_kw_value ** 0.4 - 1.02 * diameter_m


def summarize_views(views: list[dict]) -> dict:
    if not views:
        raise ValueError("no flame views")
    heights = []
    diameters = []
    for view in views:
        if view["fy"] <= 0 or view["fx"] <= 0 or view["z_m"] <= 0:
            raise ValueError("camera scale must be positive")
        if view["h_px"] <= 0 or view["w_px"] <= 0:
            raise ValueError("flame box must be positive")
        heights.append(view["h_px"] * view["z_m"] / view["fy"])
        diameters.append(view["w_px"] * view["z_m"] / view["fx"])
    height = float(np.median(heights))
    diameter = float(np.median(diameters))
    return {
        "height_m": height,
        "diameter_m": diameter,
        "q_kw": heat_release_kw(height, diameter),
        "estimated": True,
        "views": len(views),
    }


def camera_depth(world_xyz: list[float], calibration: dict, sigma: float) -> float:
    import cv2

    from fire_monitoring_inference.multiview_geometry import calibrate

    landmarks = calibration["landmarks"]
    world = np.array([item["world_m"] for item in landmarks], dtype=float)
    pixels = np.array([item["pixel"] for item in landmarks], dtype=float)
    intrinsics = np.array(calibration["intrinsics"], dtype=float)
    distortion = np.array(calibration["distortion"], dtype=float)
    poses, _ = calibrate(
        [world],
        [pixels],
        intrinsics.reshape(1, 3, 3),
        [distortion],
        sigma,
    )
    rotation = cv2.Rodrigues(poses[0][:3])[0]
    camera_point = rotation @ np.asarray(world_xyz, dtype=float) + poses[0][3:]
    depth = float(camera_point[2])
    if not math.isfinite(depth) or depth <= 0:
        raise ValueError("fire point is behind the camera")
    return depth

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


@dataclass(frozen=True)
class SourceObservation:
    camera_id: int
    class_name: str
    pixel: tuple[float, float]
    covariance_px2: tuple[tuple[float, float], tuple[float, float]]
    reliability: float
    captured_at: datetime
    image_width: int
    image_height: int


@dataclass(frozen=True)
class CameraPose:
    intrinsics: list
    distortion: list
    pose: list
    pose_covariance: list


def source_from_box(
    *,
    camera_id: int,
    class_name: str,
    bbox_xyxy: tuple[float, float, float, float],
    confidence: float,
    image_width: int,
    image_height: int,
    captured_at: datetime,
) -> SourceObservation:
    x1, y1, x2, y2 = bbox_xyxy
    if class_name == "fire":
        u, v = (x1 + x2) / 2, y2
    else:
        u, v = (x1 + x2) / 2, (y1 + y2) / 2
    u = min(max(u, 0), image_width - 1)
    v = min(max(v, 0), image_height - 1)
    sigma_u = max((x2 - x1) / 4, 1)
    sigma_v = max((y2 - y1) / 4, 1)
    reliability = min(max(confidence, 1e-3), 1 - 1e-3)
    return SourceObservation(
        camera_id=camera_id,
        class_name=class_name,
        pixel=(u, v),
        covariance_px2=((sigma_u * sigma_u, 0.0), (0.0, sigma_v * sigma_v)),
        reliability=reliability,
        captured_at=captured_at,
        image_width=image_width,
        image_height=image_height,
    )


def latest_in_window(
    observations: list[SourceObservation], now: datetime, window_ms: int
) -> list[SourceObservation]:
    cutoff = now - timedelta(milliseconds=window_ms)
    latest: dict[int, SourceObservation] = {}
    for item in observations:
        if item.captured_at < cutoff:
            continue
        current = latest.get(item.camera_id)
        if current is None or item.captured_at >= current.captured_at:
            latest[item.camera_id] = item
    return list(latest.values())


def locate_observations(
    observations: list[SourceObservation],
    poses: dict[int, CameraPose],
    locate_fn,
) -> dict:
    usable = sorted(
        (item for item in observations if item.camera_id in poses),
        key=lambda item: item.camera_id,
    )
    if len(usable) < 2:
        return {"status": "UNOBSERVABLE", "support_camera_ids": []}
    pixels = np.array([item.pixel for item in usable], dtype=np.float64)
    intrinsics = np.array([poses[item.camera_id].intrinsics for item in usable], dtype=np.float64)
    distortion = np.array([poses[item.camera_id].distortion for item in usable], dtype=np.float64)
    pose = np.array([poses[item.camera_id].pose for item in usable], dtype=np.float64)
    pose_covariance = np.array(
        [poses[item.camera_id].pose_covariance for item in usable], dtype=np.float64
    )
    pixel_covariance = np.array([item.covariance_px2 for item in usable], dtype=np.float64)
    image_area = np.array(
        [item.image_width * item.image_height for item in usable], dtype=np.float64
    )
    reliability = np.array([item.reliability for item in usable], dtype=np.float64)
    raw = locate_fn(
        pixels,
        intrinsics,
        distortion,
        pose,
        pose_covariance,
        pixel_covariance,
        image_area,
        reliability,
    )
    support = raw["support"]
    support_ids = [item.camera_id for item, flag in zip(usable, support, strict=True) if flag]
    position = {"status": raw["status"], "support_camera_ids": support_ids}
    if raw["status"] == "ESTIMATED":
        position["xyz"] = raw["xyz"]
        position["covariance"] = raw["covariance"]
    return position


def geometry_locate(*args, **kwargs):
    from .geometry import locate

    return locate(*args, **kwargs)


def build_pose(calibration: dict, sigma: float) -> CameraPose:
    from .geometry import calibrate

    world = np.array([row["world_m"] for row in calibration["landmarks"]], dtype=np.float64)
    pixels = np.array([row["pixel"] for row in calibration["landmarks"]], dtype=np.float64)
    intrinsics = np.array(calibration["intrinsics"], dtype=np.float64)
    distortion = np.array(calibration["distortion"], dtype=np.float64)
    poses, covariances = calibrate([world], [pixels], [intrinsics], [distortion], sigma)
    return CameraPose(
        intrinsics=intrinsics.tolist(),
        distortion=distortion.tolist(),
        pose=poses[0].tolist(),
        pose_covariance=covariances[0].tolist(),
    )

from __future__ import annotations

import cv2
import numpy as np
from fire_monitoring_inference.multiview_geometry import calibrate

from .spec import CONTROL_IDS, dictionary


def detect_control_points(image: np.ndarray) -> list[dict]:
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector = cv2.aruco.ArucoDetector(dictionary(), cv2.aruco.DetectorParameters())
    corners, ids, _rejected = detector.detectMarkers(gray)
    if ids is None:
        raise ValueError("画面中没有 ArUco 控制点")
    found = []
    allowed = set(CONTROL_IDS)
    for marker_corners, marker_id in zip(corners, ids.ravel(), strict=True):
        marker_id = int(marker_id)
        if marker_id not in allowed:
            continue
        center = marker_corners.reshape(4, 2).mean(axis=0)
        found.append(
            {"marker_id": marker_id, "pixel": [float(center[0]), float(center[1])]}
        )
    if len(found) < 4:
        raise ValueError(f"只检测到 {len(found)} 个控制点，至少需要 4 个")
    found.sort(key=lambda item: item["marker_id"])
    return found


def landmarks_from_points(detections: list[dict], worlds: dict[int, tuple[float, float, float]]) -> list[dict]:
    detected = {item["marker_id"] for item in detections}
    given = set(worlds)
    if detected != given:
        missing = ", ".join(str(item) for item in sorted(detected - given))
        extra = ", ".join(str(item) for item in sorted(given - detected))
        raise ValueError(f"控制点对不上，画面里未填坐标的是 [{missing}]，多填的是 [{extra}]")
    return [
        {
            "marker_id": item["marker_id"],
            "world_m": [float(axis) for axis in worlds[item["marker_id"]]],
            "pixel": [float(item["pixel"][0]), float(item["pixel"][1])],
        }
        for item in detections
    ]


def fit_extrinsics(intrinsics, distortion, landmarks: list[dict], sigma: float) -> tuple[float, np.ndarray]:
    if len(landmarks) < 4:
        raise ValueError("至少需要 4 个控制点")
    world = np.array([item["world_m"] for item in landmarks], dtype=np.float64)
    pixels = np.array([item["pixel"] for item in landmarks], dtype=np.float64)
    matrix = np.array(intrinsics, dtype=np.float64)
    dist = np.array(distortion, dtype=np.float64)
    poses, _covariances = calibrate([world], [pixels], [matrix], [dist], sigma)
    pose = poses[0]
    projected, _ = cv2.projectPoints(world, pose[:3], pose[3:], matrix, dist)
    error = projected.reshape(-1, 2) - pixels
    rms = float(np.sqrt(np.mean(np.sum(error * error, axis=1))))
    return rms, pose

from __future__ import annotations

import json

import cv2
import numpy as np

from .extrinsics import detect_control_points, fit_extrinsics, landmarks_from_points
from .intrinsics import calibrate_charuco


def decode_image(payload: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法解码图片")
    return image


def ready(raw: str | None) -> bool:
    if not raw:
        return False
    return len(json.loads(raw)["landmarks"]) >= 4


def write_intrinsics(camera, images: list[np.ndarray], paper: str) -> dict:
    result = calibrate_charuco(images, paper)
    document = {
        "intrinsics": result.intrinsics,
        "distortion": result.distortion,
        "landmarks": [],
        "intrinsics_reprojection_error_px": result.rms,
        "extrinsics_reprojection_error_px": None,
        "image_size": [result.width, result.height],
        "board": paper,
    }
    camera.calibration_json = json.dumps(document)
    return document


def write_extrinsics(camera, image: np.ndarray, worlds: dict[int, tuple[float, float, float]], sigma: float) -> dict:
    if not camera.calibration_json:
        raise ValueError("先做内参标定")
    document = json.loads(camera.calibration_json)
    if "intrinsics" not in document or "image_size" not in document:
        raise ValueError("先做内参标定")
    height, width = image.shape[:2]
    stored = document["image_size"]
    if stored != [width, height]:
        raise ValueError(f"画面是 {width}x{height}，内参是 {stored[0]}x{stored[1]}")
    detections = detect_control_points(image)
    landmarks = landmarks_from_points(detections, worlds)
    rms, _pose = fit_extrinsics(document["intrinsics"], document["distortion"], landmarks, sigma)
    document["landmarks"] = landmarks
    document["extrinsics_reprojection_error_px"] = rms
    camera.calibration_json = json.dumps(document)
    return document

from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
from pydantic import Field, FiniteFloat, PositiveInt

from .contracts import StrictModel
from .detectors.ultralytics_adapter import UltralyticsDetector
from .multiview_geometry import calibrate, locate

Pixel = tuple[FiniteFloat, FiniteFloat]
Vector3 = tuple[FiniteFloat, FiniteFloat, FiniteFloat]


class Landmark(StrictModel):
    world_m: Vector3
    pixel: Pixel


class SourceObservation(StrictModel):
    pixel: Pixel
    covariance_px2: tuple[Pixel, Pixel]
    reliability: FiniteFloat = Field(gt=0, lt=1)


class View(StrictModel):
    image: Path
    intrinsics: tuple[Vector3, Vector3, Vector3]
    distortion: list[FiniteFloat]
    landmarks: list[Landmark] = Field(min_length=4)
    source: SourceObservation | None = None


class FourViewInput(StrictModel):
    landmark_sigma_px: Annotated[FiniteFloat, Field(gt=0)]
    views: dict[PositiveInt, View] = Field(min_length=4, max_length=4)


def localize_frames(manifest: Path, model: Path, device: str) -> dict:
    request = FourViewInput.model_validate_json(manifest.read_bytes())
    if model.suffix.lower() != ".pt" or not model.is_file():
        raise ValueError(f"Expected a local YOLO26s .pt model: {model}")

    frames = []
    for camera_id, view in request.views.items():
        (fx, skew, _), (cross, fy, _), last_row = view.intrinsics
        if fx <= 0 or fy <= 0 or skew or cross or last_row != (0, 0, 1):
            raise ValueError(f"Camera {camera_id} requires OpenCV pinhole intrinsics")
        path = manifest.parent / view.image
        frame = cv2.imdecode(
            np.frombuffer(path.read_bytes(), dtype=np.uint8),
            cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION,
        )
        if frame is None:
            raise ValueError(f"Cannot decode image: {path}")
        height, width = frame.shape[:2]
        pixels = [landmark.pixel for landmark in view.landmarks]
        if view.source is not None:
            pixels.append(view.source.pixel)
            covariance = np.array(view.source.covariance_px2)
            if not np.array_equal(covariance, covariance.T):
                raise ValueError(f"Camera {camera_id} requires a symmetric source covariance")
            np.linalg.cholesky(covariance)
        if any(not (0 <= x < width and 0 <= y < height) for x, y in pixels):
            raise ValueError(f"Camera {camera_id} has a pixel outside the image")
        frames.append(frame)

    views = list(request.views.values())
    intrinsics = np.array([view.intrinsics for view in views])
    distortion = [np.array(view.distortion) for view in views]
    poses, pose_covariances = calibrate(
        [np.array([landmark.world_m for landmark in view.landmarks]) for view in views],
        [np.array([landmark.pixel for landmark in view.landmarks]) for view in views],
        intrinsics,
        distortion,
        request.landmark_sigma_px,
    )
    observed = [(i, view.source) for i, view in enumerate(views) if view.source is not None]
    indices = [i for i, _ in observed]
    position = locate(
        np.array([source.pixel for _, source in observed]),
        intrinsics[indices],
        [distortion[i] for i in indices],
        poses[indices],
        pose_covariances[indices],
        np.array([source.covariance_px2 for _, source in observed]),
        np.array([frames[i].shape[0] * frames[i].shape[1] for i in indices]),
        np.array([source.reliability for _, source in observed]),
    )
    camera_ids = list(request.views)
    position["support_camera_ids"] = [
        camera_ids[i]
        for i, supported in zip(indices, position.pop("support"), strict=True)
        if supported
    ]

    thresholds = {"fire": 0.30, "smoke": 0.35}
    detector = UltralyticsDetector(
        str(model),
        model_version="yolo26s",
        confidence=min(thresholds.values()),
        device=device,
        half=device.lower() != "cpu",
    )
    detections = detector.detect(frames)
    return {
        "position": position,
        "detections": {
            camera_id: [
                detection.model_dump(mode="json", by_alias=True)
                for detection in batch
                if detection.confidence >= thresholds[detection.class_name]
            ]
            for camera_id, batch in zip(camera_ids, detections, strict=True)
        },
    }

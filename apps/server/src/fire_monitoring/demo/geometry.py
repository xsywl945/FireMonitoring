from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

WIDTH_M = 8.0
DEPTH_M = 6.0
HEIGHT_M = 3.0
IMAGE_W = 480
IMAGE_H = 270
FPS = 8
FX = 430.0
FY = 430.0

GIMBAL_P0 = (4.0, 0.40, 2.30)
GIMBAL_YAW_DEG = 90.0
GIMBAL_TILT_ZERO = 4000.0
GROW_S = 12.0
PENDING_S = 3.0

LANDMARKS = (
    (1.0, 1.0, 0.0),
    (4.0, 1.0, 0.0),
    (7.0, 1.0, 0.0),
    (1.0, 3.0, 0.0),
    (4.0, 3.0, 0.0),
    (7.0, 3.0, 0.0),
    (1.0, 5.0, 0.0),
    (4.0, 5.0, 0.0),
    (7.0, 5.0, 0.0),
    (0.0, 2.0, 1.2),
    (0.0, 4.0, 1.2),
    (8.0, 2.0, 1.2),
    (8.0, 4.0, 1.2),
    (2.0, 0.0, 1.4),
    (6.0, 0.0, 1.4),
    (2.0, 6.0, 1.6),
    (6.0, 6.0, 1.6),
    (0.0, 3.0, 2.2),
    (8.0, 3.0, 2.2),
    (4.0, 0.0, 2.1),
    (4.0, 6.0, 2.1),
)


@dataclass(frozen=True)
class VirtualCamera:
    key: str
    name: str
    slot: int
    offset_ms: int
    eye: np.ndarray
    rotation: np.ndarray
    rvec: np.ndarray
    tvec: np.ndarray
    intrinsics: np.ndarray
    distortion: np.ndarray
    landmarks: list[dict]

    @property
    def right(self) -> np.ndarray:
        return self.rotation[:, 0]

    @property
    def down(self) -> np.ndarray:
        return self.rotation[:, 1]

    @property
    def forward(self) -> np.ndarray:
        return self.rotation[:, 2]

    def fov_y_deg(self) -> float:
        return float(np.degrees(2 * np.atan(IMAGE_H / (2 * self.intrinsics[1, 1]))))


def intrinsics_matrix() -> np.ndarray:
    return np.array(
        [[FX, 0.0, IMAGE_W / 2], [0.0, FY, IMAGE_H / 2], [0.0, 0.0, 1.0]],
        dtype=float,
    )


def _pose(eye: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
    if np.linalg.norm(right) < 1e-6:
        raise RuntimeError("相机不能垂直朝上")
    right = right / np.linalg.norm(right)
    down = np.cross(forward, right)
    down = down / np.linalg.norm(down)
    rotation = np.column_stack([right, down, forward])
    if np.linalg.det(rotation) <= 0:
        raise RuntimeError("相机姿态不是右手系")
    rvec, _ = cv2.Rodrigues(rotation.T)
    tvec = -rotation.T @ eye
    return rotation, rvec.reshape(3), tvec.reshape(3)


def project(camera: VirtualCamera, points: np.ndarray) -> np.ndarray:
    image, _ = cv2.projectPoints(
        np.asarray(points, dtype=float).reshape(-1, 1, 3),
        camera.rvec,
        camera.tvec,
        camera.intrinsics,
        camera.distortion,
    )
    return image.reshape(-1, 2)


def _inside(pixel: np.ndarray, margin: float) -> bool:
    u, v = pixel
    return margin <= u < IMAGE_W - margin and margin <= v < IMAGE_H - margin


def _landmarks(camera_without: tuple) -> list[dict]:
    rotation, rvec, tvec, matrix = camera_without
    probe = VirtualCamera(
        key="",
        name="",
        slot=0,
        offset_ms=0,
        eye=np.zeros(3),
        rotation=rotation,
        rvec=rvec,
        tvec=tvec,
        intrinsics=matrix,
        distortion=np.zeros(5),
        landmarks=[],
    )
    chosen: list[dict] = []
    pixels: list[np.ndarray] = []
    for world in LANDMARKS:
        pixel = project(probe, np.array([world]))[0]
        if not _inside(pixel, 16):
            continue
        if any(np.linalg.norm(pixel - item) < 28 for item in pixels):
            continue
        pixels.append(pixel)
        chosen.append({"world_m": [float(v) for v in world], "pixel": [float(pixel[0]), float(pixel[1])]})
        if len(chosen) == 8:
            break
    if len(chosen) < 6:
        raise RuntimeError(f"可见控制点只有 {len(chosen)} 个")
    return chosen


def build_cameras() -> list[VirtualCamera]:
    specs = (
        ("nw", "西北", 1, 0, (0.55, 5.45, 2.62), (4.4, 2.6, 0.9)),
        ("ne", "东北", 2, 40, (7.45, 5.45, 2.62), (3.6, 2.6, 0.9)),
        ("sw", "西南", 3, 80, (0.55, 0.55, 2.62), (4.4, 3.3, 0.9)),
        ("se", "东南", 4, 120, (7.45, 0.55, 2.62), (3.6, 3.3, 0.9)),
    )
    matrix = intrinsics_matrix()
    cameras = []
    for key, name, slot, offset_ms, eye, target in specs:
        eye_v = np.array(eye, dtype=float)
        rotation, rvec, tvec = _pose(eye_v, np.array(target, dtype=float))
        cameras.append(
            VirtualCamera(
                key=key,
                name=name,
                slot=slot,
                offset_ms=offset_ms,
                eye=eye_v,
                rotation=rotation,
                rvec=rvec,
                tvec=tvec,
                intrinsics=matrix,
                distortion=np.zeros(5),
                landmarks=_landmarks((rotation, rvec, tvec, matrix)),
            )
        )
    return cameras


def frame_count(duration_s: float) -> int:
    return int(round(duration_s * FPS))


def frame_time(index: int) -> float:
    return index / FPS


def billboard(camera: VirtualCamera, origin: np.ndarray, height: float, width: float) -> np.ndarray:
    side = camera.right * (width / 2)
    up = np.array([0.0, 0.0, height])
    base = np.asarray(origin, dtype=float)
    return np.stack([base - side, base + side, base - side + up, base + side + up])


def box_of(camera: VirtualCamera, corners: np.ndarray) -> list[float] | None:
    cam = (corners - camera.eye) @ camera.rotation
    if np.any(cam[:, 2] <= 0.05):
        return None
    pixels = project(camera, corners)
    x0 = max(0.0, float(np.min(pixels[:, 0])))
    y0 = max(0.0, float(np.min(pixels[:, 1])))
    x1 = min(IMAGE_W - 1.0, float(np.max(pixels[:, 0])))
    y1 = min(IMAGE_H - 1.0, float(np.max(pixels[:, 1])))
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    if x0 >= IMAGE_W or y0 >= IMAGE_H:
        return None
    return [x0, y0, x1, y1]

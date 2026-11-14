from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .spec import MAX_INTRINSIC_RMS_PX, MIN_CHARUCO_CORNERS, MIN_INTRINSIC_VIEWS, charuco_board


@dataclass(frozen=True)
class IntrinsicResult:
    intrinsics: list[list[float]]
    distortion: list[float]
    rms: float
    width: int
    height: int
    views: int


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def calibrate_charuco(images: list[np.ndarray], paper: str) -> IntrinsicResult:
    if len(images) < MIN_INTRINSIC_VIEWS:
        raise ValueError(f"至少需要 {MIN_INTRINSIC_VIEWS} 张标定板图片，现在是 {len(images)} 张")
    board = charuco_board(paper)
    detector = cv2.aruco.CharucoDetector(board)
    object_points = []
    image_points = []
    image_size = None
    for index, image in enumerate(images, start=1):
        gray = _gray(image)
        size = (gray.shape[1], gray.shape[0])
        if image_size is None:
            image_size = size
        elif size != image_size:
            raise ValueError(
                f"第 {index} 张是 {size[0]}x{size[1]}，前面的图片是 {image_size[0]}x{image_size[1]}"
            )
        corners, ids, _, _ = detector.detectBoard(gray)
        count = 0 if ids is None else len(ids)
        if count < MIN_CHARUCO_CORNERS:
            raise ValueError(f"第 {index} 张只找到 {count} 个角点")
        obj, img = board.matchImagePoints(corners, ids)
        object_points.append(obj)
        image_points.append(img)
    rms, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        object_points,
        image_points,
        image_size,
        None,
        None,
        flags=cv2.CALIB_FIX_K3,
    )
    rms = float(rms)
    if rms >= MAX_INTRINSIC_RMS_PX:
        raise ValueError(f"重投影误差 {rms:.3f} px，超过 {MAX_INTRINSIC_RMS_PX} px，不保存")
    flat = np.zeros(5, dtype=np.float64)
    coeffs = dist_coeffs.ravel()
    flat[: coeffs.size] = coeffs[:5]
    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    cx = float(camera_matrix[0, 2])
    cy = float(camera_matrix[1, 2])
    width, height = image_size
    return IntrinsicResult(
        intrinsics=[[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
        distortion=[float(item) for item in flat],
        rms=rms,
        width=width,
        height=height,
        views=len(images),
    )

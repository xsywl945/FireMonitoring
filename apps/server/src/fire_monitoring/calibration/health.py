from __future__ import annotations

import cv2
import numpy as np

from .spec import BLUR_LAPLACIAN_VARIANCE


def assess_frame(previous: np.ndarray | None, image: np.ndarray) -> tuple[str, np.ndarray]:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("frame must be BGR")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if (
        previous is not None
        and previous.shape == gray.shape
        and cv2.countNonZero(cv2.absdiff(previous, gray)) == 0
    ):
        return "frozen", gray
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < BLUR_LAPLACIAN_VARIANCE:
        return "blur", gray
    return "ok", gray

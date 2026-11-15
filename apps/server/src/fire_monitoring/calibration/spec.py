from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

DICTIONARY_ID = cv2.aruco.DICT_4X4_50
CONTROL_IDS = tuple(range(40, 48))
MIN_INTRINSIC_VIEWS = 10
MIN_CHARUCO_CORNERS = 8
MAX_INTRINSIC_RMS_PX = 0.5
BLUR_LAPLACIAN_VARIANCE = 80.0


@dataclass(frozen=True)
class CharucoPaper:
    page_mm: tuple[float, float]
    squares: tuple[int, int]
    square_mm: float
    marker_mm: float


@dataclass(frozen=True)
class MarkerPaper:
    page_mm: tuple[float, float]
    marker_mm: float


CHARUCO = {
    "a4": CharucoPaper((210.0, 297.0), (5, 8), 26.0, 18.0),
    "a3": CharucoPaper((297.0, 420.0), (7, 10), 34.0, 24.0),
}

MARKERS = {
    "a4": MarkerPaper((210.0, 297.0), 42.0),
    "a3": MarkerPaper((297.0, 420.0), 64.0),
}


def paper(kind: str, name: str):
    table = CHARUCO if kind == "charuco" else MARKERS
    if name not in table:
        raise ValueError("纸张必须是 a4 或 a3")
    return table[name]


def dictionary():
    return cv2.aruco.getPredefinedDictionary(DICTIONARY_ID)


def charuco_board(name: str) -> cv2.aruco.CharucoBoard:
    spec = paper("charuco", name)
    return cv2.aruco.CharucoBoard(
        spec.squares,
        spec.square_mm / 1000.0,
        spec.marker_mm / 1000.0,
        dictionary(),
    )


def marker_bits(marker_id: int) -> np.ndarray:
    image = cv2.aruco.generateImageMarker(dictionary(), marker_id, 6, borderBits=1)
    return image < 128


def marker_squares(squares: tuple[int, int]) -> list[tuple[int, int, int]]:
    count_x, count_y = squares
    found = []
    marker_id = 0
    for row in range(count_y):
        for col in range(count_x):
            if (col + row) % 2 == 0:
                continue
            found.append((marker_id, col, row))
            marker_id += 1
    return found


def label_cell(col: int, row: int) -> tuple[int, int]:
    if row % 2 == 0:
        return col, row + 1
    return col, row - 1

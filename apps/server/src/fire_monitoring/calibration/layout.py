from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .spec import CONTROL_IDS, label_cell, marker_bits, marker_squares, paper


@dataclass(frozen=True)
class Rect:
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float


@dataclass(frozen=True)
class Label:
    x_mm: float
    y_mm: float
    text: str
    size_pt: float
    white: bool


@dataclass(frozen=True)
class Page:
    width_mm: float
    height_mm: float
    rects: tuple[Rect, ...]
    labels: tuple[Label, ...]


def _scale_bar(width_mm: float, height_mm: float) -> tuple[Rect, Label]:
    return (
        Rect(16.0, height_mm - 14.0, 100.0, 0.5),
        Label(66.0, height_mm - 8.0, "100 mm", 9, False),
    )


def charuco_page(name: str) -> Page:
    spec = paper("charuco", name)
    width, height = spec.page_mm
    board_w = spec.squares[0] * spec.square_mm
    board_h = spec.squares[1] * spec.square_mm
    origin_x = (width - board_w) / 2
    origin_y = 24.0
    rects: list[Rect] = []
    labels = [
        Label(
            width / 2,
            8.0,
            f"ChArUco DICT_4X4_50  {name.upper()}  PRINT 100%  DO NOT SCALE",
            10,
            False,
        ),
        Label(
            width / 2,
            16.0,
            f"square {spec.square_mm:.2f} mm   marker {spec.marker_mm:.2f} mm",
            10,
            False,
        ),
    ]
    for row in range(spec.squares[1]):
        for col in range(spec.squares[0]):
            if (col + row) % 2 != 0:
                continue
            rects.append(
                Rect(
                    origin_x + col * spec.square_mm,
                    origin_y + row * spec.square_mm,
                    spec.square_mm,
                    spec.square_mm,
                )
            )
    cell = spec.marker_mm / 6
    for marker_id, col, row in marker_squares(spec.squares):
        left = origin_x + (col + 0.5) * spec.square_mm - spec.marker_mm / 2
        top = origin_y + (row + 0.5) * spec.square_mm - spec.marker_mm / 2
        bits = marker_bits(marker_id)
        for bit_row in range(6):
            for bit_col in range(6):
                if not bits[bit_row, bit_col]:
                    continue
                rects.append(
                    Rect(left + bit_col * cell, top + bit_row * cell, cell, cell)
                )
        label_col, label_row = label_cell(col, row)
        labels.append(
            Label(
                origin_x + (label_col + 0.5) * spec.square_mm,
                origin_y + (label_row + 0.5) * spec.square_mm,
                str(marker_id),
                8,
                True,
            )
        )
    bar, caption = _scale_bar(width, height)
    rects.append(bar)
    labels.append(caption)
    return Page(width, height, tuple(rects), tuple(labels))


def marker_page(name: str) -> Page:
    spec = paper("markers", name)
    width, height = spec.page_mm
    columns, rows = 2, 4
    margin_x = 16.0
    margin_y = 22.0
    cell_w = (width - 2 * margin_x) / columns
    cell_h = (height - margin_y - 18.0) / rows
    bit = spec.marker_mm / 6
    rects: list[Rect] = []
    labels = [
        Label(
            width / 2,
            8.0,
            f"ArUco DICT_4X4_50  {name.upper()}  PRINT 100%  DO NOT SCALE",
            10,
            False,
        ),
        Label(
            width / 2,
            15.0,
            f"marker {spec.marker_mm:.2f} mm   number is beside the code   measure the center",
            9,
            False,
        ),
    ]
    for index, marker_id in enumerate(CONTROL_IDS):
        col = index % columns
        row = index // columns
        left = margin_x + col * cell_w + (cell_w - spec.marker_mm) / 2
        top = margin_y + row * cell_h + 2.0
        bits = marker_bits(marker_id)
        for bit_row in range(6):
            for bit_col in range(6):
                if not bits[bit_row, bit_col]:
                    continue
                rects.append(Rect(left + bit_col * bit, top + bit_row * bit, bit, bit))
        labels.append(
            Label(
                margin_x + (col + 0.5) * cell_w,
                top + spec.marker_mm + 5.0,
                str(marker_id),
                14,
                False,
            )
        )
    bar, caption = _scale_bar(width, height)
    rects.append(bar)
    labels.append(caption)
    return Page(width, height, tuple(rects), tuple(labels))


def rasterize(page: Page, pixels_per_mm: float) -> np.ndarray:
    width = int(round(page.width_mm * pixels_per_mm))
    height = int(round(page.height_mm * pixels_per_mm))
    image = np.full((height, width), 255, np.uint8)
    for rect in page.rects:
        x0 = int(round(rect.x_mm * pixels_per_mm))
        y0 = int(round(rect.y_mm * pixels_per_mm))
        x1 = int(round((rect.x_mm + rect.w_mm) * pixels_per_mm))
        y1 = int(round((rect.y_mm + rect.h_mm) * pixels_per_mm))
        image[y0:y1, x0:x1] = 0
    for label in page.labels:
        scale = label.size_pt / 18
        thickness = 1
        color = 255 if label.white else 0
        size, _ = cv2.getTextSize(label.text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
        x = int(round(label.x_mm * pixels_per_mm - size[0] / 2))
        y = int(round(label.y_mm * pixels_per_mm + size[1] / 2))
        cv2.putText(
            image,
            label.text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
    return image

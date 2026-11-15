from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class PersonBox:
    xyxy: tuple[float, float, float, float]
    score: float


class PersonDetector(Protocol):
    def detect(self, image) -> list[PersonBox]: ...


class ScriptedPeople:
    def __init__(self, boxes: list[PersonBox] | None = None, points: list | None = None) -> None:
        self.boxes = list(boxes or [])
        self.points = [np.asarray(item, dtype=float) for item in (points or [])]

    def detect(self, image) -> list[PersonBox]:
        return list(self.boxes)

    def world_points(self) -> list[np.ndarray]:
        return list(self.points)


class YoloCocoPersonDetector:
    """COCO pretrained person class. The weight file is not downloaded in CI."""

    def __init__(self, weights: str) -> None:
        self.weights = weights
        self._model = None

    def detect(self, image) -> list[PersonBox]:
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.weights)
        found = []
        for result in self._model.predict(image, classes=[0], verbose=False):
            if result.boxes is None:
                continue
            for box, score in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), strict=True):
                found.append(PersonBox(xyxy=(box[0], box[1], box[2], box[3]), score=float(score)))
        return found


def nearest_distance(fire, persons) -> float | None:
    if fire is None or not persons:
        return None
    origin = np.asarray(fire, dtype=float)
    return float(min(np.linalg.norm(np.asarray(person, dtype=float) - origin) for person in persons))

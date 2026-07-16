from __future__ import annotations

from typing import Any

from ..contracts import Detection


class UltralyticsDetector:
    """Optional YOLO adapter; importing this module does not import torch/ultralytics."""

    def __init__(
        self,
        model_path: str,
        *,
        model_version: str,
        imgsz: int = 640,
        confidence: float = 0.25,
        device: str | int | None = None,
        half: bool = True,
        class_aliases: dict[str, str] | None = None,
    ) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - requires optional GPU stack
            raise RuntimeError(
                "Ultralytics is optional. Install a compatible PyTorch wheel, then "
                "install fire-monitoring-inference[yolo]."
            ) from exc
        self._model = YOLO(model_path)
        self.model_version = model_version
        self.imgsz = imgsz
        self.confidence = confidence
        self.device = device
        self.half = half
        self.class_aliases = {key.lower(): value for key, value in (class_aliases or {}).items()}

    def detect(self, images: list[Any]) -> list[list[Detection]]:
        results = self._model.predict(
            source=images,
            imgsz=self.imgsz,
            conf=self.confidence,
            device=self.device,
            half=self.half,
            verbose=False,
        )
        batches: list[list[Detection]] = []
        for result in results:
            detections: list[Detection] = []
            names = result.names
            for box in result.boxes:
                raw_name = str(names[int(box.cls.item())]).lower()
                class_name = self.class_aliases.get(raw_name, raw_name)
                if class_name not in {"fire", "smoke"}:
                    continue
                xyxy = tuple(float(value) for value in box.xyxy[0].tolist())
                detections.append(
                    Detection(
                        className=class_name,
                        confidence=float(box.conf.item()),
                        bboxXyxy=xyxy,
                    )
                )
            batches.append(detections)
        return batches

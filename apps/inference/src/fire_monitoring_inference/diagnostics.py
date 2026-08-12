from __future__ import annotations

from pathlib import Path
from typing import Any


def local_yolo_diagnostics(model_path: Path, *, device_index: int = 0) -> dict[str, Any]:
    """Verify the isolated CUDA runtime and the trained model's class contract."""
    try:
        import cv2
        import torch
        import ultralytics
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - depends on optional local GPU stack
        raise RuntimeError(
            "local YOLO dependencies are incomplete; run setup-local-yolo.ps1"
        ) from exc

    if not model_path.is_file():
        raise RuntimeError(f"model file does not exist: {model_path}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to PyTorch")
    if device_index < 0 or device_index >= torch.cuda.device_count():
        raise RuntimeError(f"CUDA device {device_index} does not exist")

    device = f"cuda:{device_index}"
    tensor_result = float((torch.ones(1, device=device) * 2).item())
    model = YOLO(str(model_path))
    raw_names = model.names
    if isinstance(raw_names, dict):
        names = {int(key): str(value).lower() for key, value in raw_names.items()}
    else:
        names = {index: str(value).lower() for index, value in enumerate(raw_names)}
    expected = {0: "fire", 1: "smoke"}
    if names != expected:
        raise RuntimeError(f"unexpected model classes: {names}; expected {expected}")

    return {
        "torch": str(torch.__version__),
        "torchCuda": str(torch.version.cuda),
        "ultralytics": str(ultralytics.__version__),
        "opencv": str(cv2.__version__),
        "gpu": str(torch.cuda.get_device_name(device_index)),
        "capability": list(torch.cuda.get_device_capability(device_index)),
        "cudaTensorCheck": tensor_result,
        "classes": names,
        "model": str(model_path.resolve()),
    }

import numpy as np

from fire_monitoring.calibration.health import assess_frame
from fire_monitoring.detection.health import FaultTracker


def _sharp() -> np.ndarray:
    image = np.zeros((180, 240, 3), np.uint8)
    image[::8, :, :] = 255
    image[:, ::8, :] = 255
    return image


def _blurry(shift: int) -> np.ndarray:
    image = np.zeros((180, 240, 3), np.uint8)
    image[:, :, 0] = np.linspace(shift, 40 + shift, 240, dtype=np.uint8)
    return image


def test_freeze_blur_and_offline_on_synthetic_frames() -> None:
    sharp = _sharp()
    status, gray = assess_frame(None, sharp)
    assert status == "ok"
    tracker = FaultTracker(freeze_seconds=5, offline_seconds=3)
    assert tracker.update(1, status, 0) == []

    status, _same = assess_frame(gray, sharp)
    assert status == "frozen"
    assert tracker.update(1, status, 1) == []
    frozen = tracker.update(1, status, 6)
    assert [item.kind for item in frozen] == ["FROZEN"]
    assert tracker.update(1, status, 9) == []

    blurry = _blurry(0)
    status, gray = assess_frame(None, blurry)
    assert status == "blur"
    status, _gray = assess_frame(gray, _blurry(5))
    assert status == "blur"
    blur_tracker = FaultTracker(freeze_seconds=5, offline_seconds=3)
    assert [item.kind for item in blur_tracker.update(2, status, 0)] == ["BLUR"]
    assert blur_tracker.update(2, status, 1) == []

    assert tracker.update(3, "offline", 0) == []
    offline = tracker.update(3, "offline", 3)
    assert [item.kind for item in offline] == ["OFFLINE"]
    assert tracker.update(3, "offline", 6) == []
    assert tracker.update(3, "ok", 7) == []
    assert tracker.update(3, "offline", 10) == []
    again = tracker.update(3, "offline", 13)
    assert [item.kind for item in again] == ["OFFLINE"]

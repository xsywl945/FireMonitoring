import numpy as np

from fire_monitoring.detection.health import HealthTracker, blur_variance


def test_freeze_blur_and_offline_on_synthetic_frames() -> None:
    sharp = np.zeros((32, 32), np.uint8)
    sharp[::2, :] = 255
    flat = np.full((32, 32), 128, np.uint8)
    assert blur_variance(sharp) > blur_variance(flat)
    tracker = HealthTracker(freeze_seconds=5, blur_variance_limit=blur_variance(sharp), offline_seconds=3)

    first, faults = tracker.observe(1, sharp, 0)
    assert first.online and not first.frozen and not first.blur and faults == []
    second, faults = tracker.observe(1, sharp, 4.9)
    assert not second.frozen and faults == []
    frozen, faults = tracker.observe(1, sharp.copy(), 5)
    assert frozen.frozen and not frozen.blur
    assert [item.kind for item in faults] == ["FROZEN"]
    again, faults = tracker.observe(1, sharp, 9)
    assert again.frozen and faults == []

    changed, faults = tracker.observe(1, flat, 10)
    assert not changed.frozen and changed.blur
    assert [item.kind for item in faults] == ["BLUR"]

    other, faults = tracker.observe(2, None, 0)
    assert not other.online and faults == []
    offline, faults = tracker.observe(2, None, 3)
    assert [item.kind for item in faults] == ["OFFLINE"]
    held, faults = tracker.observe(2, None, 6)
    assert not held.online and faults == []

    back, faults = tracker.observe(1, None, 11)
    assert not back.online and faults == []
    gone, faults = tracker.observe(1, None, 14)
    assert [item.kind for item in faults] == ["OFFLINE"]

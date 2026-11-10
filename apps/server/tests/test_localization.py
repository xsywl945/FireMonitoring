from datetime import UTC, datetime, timedelta

from fire_monitoring.config import load_config
from fire_monitoring.detection.ingest import DetectionHit, DetectionState, consume_frame
from fire_monitoring.localization.observe import (
    CameraPose,
    latest_in_window,
    locate_observations,
    source_from_box,
)

EXAMPLE = __import__("pathlib").Path(__file__).resolve().parents[3] / "config.example.json"


def _pose() -> CameraPose:
    return CameraPose(
        intrinsics=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        distortion=[0, 0, 0, 0, 0],
        pose=[0, 0, 0, 0, 0, 1],
        pose_covariance=[[0.0] * 6 for _ in range(6)],
    )


def test_source_pixel_covariance_and_reliability() -> None:
    now = datetime(2026, 11, 10, tzinfo=UTC)
    fire = source_from_box(
        camera_id=1,
        class_name="fire",
        bbox_xyxy=(10, 20, 50, 80),
        confidence=0.8,
        image_width=100,
        image_height=100,
        captured_at=now,
    )
    smoke = source_from_box(
        camera_id=1,
        class_name="smoke",
        bbox_xyxy=(0, 0, 40, 20),
        confidence=1,
        image_width=100,
        image_height=100,
        captured_at=now,
    )
    assert fire.pixel == (30, 80)
    assert fire.covariance_px2 == ((100, 0), (0, 225))
    assert fire.reliability == 0.8
    assert smoke.pixel == (20, 10)
    assert smoke.reliability == 1 - 1e-3


def test_window_keeps_latest_observation_per_camera() -> None:
    now = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    old = source_from_box(
        camera_id=1,
        class_name="fire",
        bbox_xyxy=(0, 0, 8, 8),
        confidence=0.4,
        image_width=100,
        image_height=100,
        captured_at=now - timedelta(seconds=2),
    )
    first = source_from_box(
        camera_id=1,
        class_name="fire",
        bbox_xyxy=(10, 10, 20, 20),
        confidence=0.5,
        image_width=100,
        image_height=100,
        captured_at=now - timedelta(milliseconds=200),
    )
    second = source_from_box(
        camera_id=1,
        class_name="fire",
        bbox_xyxy=(12, 12, 22, 22),
        confidence=0.9,
        image_width=100,
        image_height=100,
        captured_at=now,
    )
    other = source_from_box(
        camera_id=2,
        class_name="fire",
        bbox_xyxy=(30, 30, 40, 40),
        confidence=0.6,
        image_width=100,
        image_height=100,
        captured_at=now - timedelta(milliseconds=100),
    )
    selected = latest_in_window([old, first, other, second], now, 500)
    by_camera = {item.camera_id: item for item in selected}
    assert set(by_camera) == {1, 2}
    assert by_camera[1].reliability == 0.9


def test_locate_maps_support_and_skips_single_view() -> None:
    now = datetime(2026, 11, 10, tzinfo=UTC)
    first = source_from_box(
        camera_id=2,
        class_name="fire",
        bbox_xyxy=(0, 0, 20, 20),
        confidence=0.7,
        image_width=64,
        image_height=64,
        captured_at=now,
    )
    second = source_from_box(
        camera_id=1,
        class_name="fire",
        bbox_xyxy=(4, 4, 16, 16),
        confidence=0.6,
        image_width=64,
        image_height=64,
        captured_at=now,
    )
    calls = []

    def locate_fn(pixels, intrinsics, distortion, poses, pose_covariance, pixel_covariance, image_area, reliability):
        calls.append(pixels.copy())
        return {
            "status": "ESTIMATED",
            "xyz": [1.0, 2.0, 0.0],
            "covariance": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "support": [True, False],
        }

    poses = {1: _pose(), 2: _pose()}
    position = locate_observations([first, second], poses, locate_fn)
    assert calls[0][0].tolist() == list(second.pixel)
    assert calls[0][1].tolist() == list(first.pixel)
    assert position["status"] == "ESTIMATED"
    assert position["xyz"] == [1.0, 2.0, 0.0]
    assert position["support_camera_ids"] == [1]

    calls.clear()
    missing = locate_observations([second], poses, locate_fn)
    assert missing == {"status": "UNOBSERVABLE", "support_camera_ids": []}
    assert calls == []


def test_confirmed_detection_collects_window_and_fire_pixel() -> None:
    config = load_config(EXAMPLE)
    config.temporal.n = 2
    config.temporal.m = 3
    config.temporal.candidate_n = 1
    config.localization.window_ms = 500
    state = DetectionState()
    drafts = []
    start = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    fire = DetectionHit("fire", 0.82, (10, 20, 50, 80))
    weak_smoke = DetectionHit("smoke", 0.31, (0, 0, 40, 40))

    def alert(draft) -> None:
        drafts.append(draft)

    consume_frame(
        room_id=7,
        camera_id=2,
        bound_camera_ids=[1, 2],
        detections=[fire],
        jpeg=b"cam2",
        width=100,
        height=100,
        timestamp=start,
        state=state,
        config=config,
        on_alert=alert,
    )
    consume_frame(
        room_id=7,
        camera_id=1,
        bound_camera_ids=[1, 2],
        detections=[fire, weak_smoke],
        jpeg=b"cam1-a",
        width=100,
        height=100,
        timestamp=start,
        state=state,
        config=config,
        on_alert=alert,
    )
    snapshot = consume_frame(
        room_id=7,
        camera_id=1,
        bound_camera_ids=[1, 2],
        detections=[fire, weak_smoke],
        jpeg=b"cam1-b",
        width=100,
        height=100,
        timestamp=start + timedelta(milliseconds=100),
        state=state,
        config=config,
        on_alert=alert,
    )
    assert snapshot["states"]["fire"] == "CONFIRMED"
    assert snapshot["states"]["smoke"] == "NORMAL"
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.alert_type == "FIRE"
    assert {item.camera_id for item in draft.sources} == {1, 2}
    own = next(item for item in draft.sources if item.camera_id == 1)
    assert own.pixel == (30, 80)
    assert own.reliability == 0.82
    assert {frame.jpeg for frame in draft.frames} == {b"cam2", b"cam1-b"}
    assert draft.pump_observations[0]["class_name"] == "fire"

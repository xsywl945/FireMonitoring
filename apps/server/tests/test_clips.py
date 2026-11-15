from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from fire_monitoring.db import Base, make_engine, make_session_factory
from fire_monitoring.detection.capture import CapturedFrame, FrameBuffer
from fire_monitoring.detection.clips import ClipRecorder, encode_mp4, select_window
from fire_monitoring.events.hub import EventHub
from fire_monitoring.evidence.store import MemoryStore
from fire_monitoring.models import Alert, AlertClip, Room


def _frame(when: datetime, value: int) -> CapturedFrame:
    image = np.full((16, 16, 3), value, np.uint8)
    return CapturedFrame(image=image, jpeg=b"", captured_at=when, width=16, height=16)


def test_window_keeps_five_seconds_before_and_ten_after() -> None:
    alert_at = datetime(2026, 11, 14, tzinfo=UTC)
    offsets = (-6, -5, -1, 0, 9, 10, 11)
    frames = [_frame(alert_at + timedelta(seconds=offset), index) for index, offset in enumerate(offsets)]
    chosen = select_window(frames, alert_at)
    kept = [(frame.captured_at - alert_at).total_seconds() for frame in chosen]
    assert kept == [-5, -1, 0, 9, 10]


def test_encode_mp4_roundtrip() -> None:
    alert_at = datetime(2026, 11, 14, tzinfo=UTC)
    frames = [_frame(alert_at + timedelta(seconds=index), index * 40) for index in range(4)]
    data = encode_mp4(frames, 2)
    path = Path("/tmp/fire-clip-test.mp4")
    path.write_bytes(data)
    capture = cv2.VideoCapture(str(path))
    count = 0
    while True:
        ok, _image = capture.read()
        if not ok:
            break
        count += 1
    capture.release()
    path.unlink()
    assert count == 4


def test_recorder_stores_mp4(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'clips.db'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    now = datetime.now(UTC)
    session.add(Room(name="101", scene_type="classroom", created_at=now))
    session.commit()
    room = session.query(Room).one()
    session.add(
        Alert(
            room_id=room.id,
            alert_type="FIRE",
            started_at=now,
            observations_json="[]",
            status="OPEN",
        )
    )
    session.commit()
    alert = session.query(Alert).one()
    session.close()

    buffer = FrameBuffer(ring_fps=2, ring_seconds=15)
    for index in range(6):
        when = now - timedelta(seconds=5 - index)
        buffer.push(_frame(when, index * 20), float(index))

    class _Capture:
        pass

    capture = _Capture()
    capture.buffer = buffer
    evidence = MemoryStore()
    events = EventHub()

    class _Job:
        alert_id = alert.id
        room_id = room.id
        started_at = now

    recorder = ClipRecorder(evidence, factory, events, lambda: None, post=0)
    recorder.schedule(_Job(), {7: capture})
    recorder.stop()
    stored = factory()
    clip = stored.query(AlertClip).one()
    assert clip.camera_id == 7
    assert clip.alert_id == alert.id
    data, content_type = evidence.get(clip.object_key)
    assert content_type == "video/mp4"
    assert data[:3] != b""
    assert events.published[-1]["kind"] == "CLIP"

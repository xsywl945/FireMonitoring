from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..config import AppConfig
from ..localization.observe import SourceObservation, locate_position
from ..models import Alert, AlertEvent, AlertFrame, Camera, Room
from ..pump.bridge import trigger_pump
from ..sms.service import SmsService


def _source_payload(item: SourceObservation) -> dict:
    return {
        "camera_id": item.camera_id,
        "class_name": item.class_name,
        "pixel": [item.pixel[0], item.pixel[1]],
        "covariance_px2": [list(row) for row in item.covariance_px2],
        "reliability": item.reliability,
        "captured_at": item.captured_at.isoformat(),
    }


def record_event(session: Session, *, room_id: int, alert_id: int, kind: str, detail: dict) -> dict:
    occurred_at = datetime.now(UTC)
    session.add(
        AlertEvent(
            room_id=room_id,
            alert_id=alert_id,
            kind=kind,
            detail_json=json.dumps(detail, ensure_ascii=False),
            occurred_at=occurred_at,
        )
    )
    return {
        "kind": kind,
        "alert_id": alert_id,
        "room_id": room_id,
        "occurred_at": occurred_at.isoformat(),
        **detail,
    }


def record_alert(
    session: Session,
    *,
    room_id: int,
    alert_type: str,
    started_at: datetime,
    sources: list[SourceObservation],
    frames: list,
    evidence,
) -> tuple[Alert, dict]:
    room = session.get(Room, room_id)
    if room is None:
        raise RuntimeError(f"room {room_id} does not exist")
    alert = Alert(
        room_id=room_id,
        alert_type=alert_type,
        started_at=started_at,
        position_json=None,
        observations_json=json.dumps(
            [_source_payload(item) for item in sources], ensure_ascii=False
        ),
    )
    session.add(alert)
    session.flush()
    for frame in frames:
        key = f"alerts/{alert.id}/{frame.camera_id}.jpg"
        evidence.put(key, frame.jpeg, "image/jpeg")
        session.add(
            AlertFrame(
                alert_id=alert.id,
                camera_id=frame.camera_id,
                object_key=key,
                captured_at=frame.captured_at,
            )
        )
    payload = record_event(
        session,
        room_id=room_id,
        alert_id=alert.id,
        kind="CONFIRMED",
        detail={"alert_type": alert_type, "room_name": room.name},
    )
    session.commit()
    return alert, payload


def write_position(session: Session, alert_id: int, position: dict) -> dict:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise RuntimeError(f"alert {alert_id} does not exist")
    alert.position_json = json.dumps(position)
    kind = "LOCALIZED" if position.get("status") == "ESTIMATED" else "UNOBSERVABLE"
    payload = record_event(
        session,
        room_id=alert.room_id,
        alert_id=alert.id,
        kind=kind,
        detail={"status": position.get("status")},
    )
    session.commit()
    return payload


def write_analysis(session: Session, alert_id: int, analysis: dict) -> dict:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise RuntimeError(f"alert {alert_id} does not exist")
    alert.analysis_json = json.dumps(analysis, ensure_ascii=False)
    payload = record_event(
        session,
        room_id=alert.room_id,
        alert_id=alert.id,
        kind="ANALYSIS",
        detail={"status": analysis.get("status")},
    )
    session.commit()
    return payload


def notify_room(
    session: Session,
    sms: SmsService,
    *,
    alert_id: int,
    room_id: int,
    room_name: str,
    level: str,
    method: str,
    when: datetime,
) -> dict | None:
    sent = sms.notify(
        session,
        room_id=room_id,
        room_name=room_name,
        level=level,
        method=method,
        when=when,
    )
    if not sent:
        session.commit()
        return None
    payload = record_event(
        session,
        room_id=room_id,
        alert_id=alert_id,
        kind="SMS",
        detail={"room_name": room_name, "level": level, "method": method},
    )
    session.commit()
    return payload


def actuate(
    session: Session,
    pump,
    *,
    alert_id: int,
    room_id: int,
    alert_type: str,
    observations: list[dict],
    analysis: dict | None,
    captured_at: datetime,
    model_version: str,
) -> dict | None:
    if pump is None or not observations:
        return None
    trigger_pump(
        pump,
        room_id=room_id,
        alert_type=alert_type,
        observations=observations,
        analysis=analysis,
        captured_at=captured_at,
        model_version=model_version,
    )
    payload = record_event(
        session,
        room_id=room_id,
        alert_id=alert_id,
        kind="PUMP",
        detail={"alert_type": alert_type},
    )
    session.commit()
    return payload


def rerun_analysis(session: Session, alert: Alert, evidence, analyzer, config, localizer=None) -> dict:
    from ..analysis.compose import compose, samples_from_inputs
    from ..detection.ingest import FrameShot

    room = session.get(Room, alert.room_id)
    if room is None:
        raise RuntimeError(f"room {alert.room_id} does not exist")
    stored = session.query(AlertFrame).filter(AlertFrame.alert_id == alert.id).all()
    previous = json.loads(alert.analysis_json) if alert.analysis_json else {}
    inputs = previous.get("inputs") or {}
    boxes = {item["camera_id"]: tuple(item["bbox"]) for item in inputs.get("samples", [])}
    sizes = {
        item["camera_id"]: (item["width"], item["height"]) for item in inputs.get("samples", [])
    }
    frames = []
    for frame in stored:
        blob = evidence.get(frame.object_key)[0]
        width, height = sizes.get(frame.camera_id, (0, 0))
        frames.append(
            FrameShot(
                camera_id=frame.camera_id,
                jpeg=blob,
                captured_at=frame.captured_at,
                width=width,
                height=height,
                fire_box=boxes.get(frame.camera_id),
            )
        )
    before = evidence.get(inputs["before_key"])[0] if inputs.get("before_key") else None
    after = evidence.get(inputs["after_key"])[0] if inputs.get("after_key") else None
    call = analyzer.analyze(alert.id, frames, before, after)
    position = json.loads(alert.position_json) if alert.position_json else None
    calibrations = {}
    for frame in stored:
        camera = session.get(Camera, frame.camera_id)
        if camera is not None and camera.calibration_json:
            calibrations[camera.id] = json.loads(camera.calibration_json)
    combustibles = []
    if room.floor_plan_json:
        combustibles = json.loads(room.floor_plan_json).get("combustibles", [])
    document = compose(
        config,
        call=call,
        room_name=room.name,
        configured_scene=room.scene_type,
        position=position,
        samples=samples_from_inputs(inputs.get("samples", [])),
        frames=frames,
        calibrations=calibrations,
        combustibles=combustibles,
        localizer=localizer,
    )
    if inputs.get("before_key"):
        document["inputs"]["before_key"] = inputs["before_key"]
    if inputs.get("after_key"):
        document["inputs"]["after_key"] = inputs["after_key"]
    alert.analysis_json = json.dumps(document, ensure_ascii=False)
    session.commit()
    return document

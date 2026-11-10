from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import AppConfig
from ..localization.observe import SourceObservation, locate_position
from ..models import Alert, AlertFrame, Room
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


def confirm_alert(
    session: Session,
    *,
    room_id: int,
    alert_type: str,
    started_at: datetime,
    sources: list[SourceObservation],
    calibrations: dict,
    frames: list,
    pump_observations: list[dict],
    config: AppConfig,
    evidence,
    analyzer,
    sms: SmsService,
    pump,
    localizer=None,
) -> Alert:
    room = session.get(Room, room_id)
    room_name = room.name
    position = locate_position(config, frames, calibrations, sources, localizer=localizer)
    alert = Alert(
        room_id=room_id,
        alert_type=alert_type,
        started_at=started_at,
        position_json=json.dumps(position),
        observations_json=json.dumps([_source_payload(item) for item in sources], ensure_ascii=False),
    )
    session.add(alert)
    session.flush()
    jpegs: list[bytes] = []
    for frame in frames:
        key = f"alerts/{alert.id}/{frame.camera_id}.jpg"
        evidence.put(key, frame.jpeg, "image/jpeg")
        jpegs.append(frame.jpeg)
        session.add(
            AlertFrame(
                alert_id=alert.id,
                camera_id=frame.camera_id,
                object_key=key,
                captured_at=frame.captured_at,
            )
        )
    analysis = None
    if config.llm.enabled and analyzer is not None and jpegs:
        analysis = analyzer.analyze(alert.id, jpegs)
        alert.analysis_json = json.dumps(analysis, ensure_ascii=False)
    session.commit()
    sms.notify(
        session,
        room_id=room_id,
        room_name=room_name,
        alert_type=alert_type,
        when=started_at,
    )
    session.commit()
    if pump is not None and pump_observations:
        trigger_pump(
            pump,
            room_id=room_id,
            alert_type=alert_type,
            observations=pump_observations,
            analysis=analysis,
            captured_at=started_at,
            model_version=config.model.version,
        )
    return alert


def rerun_analysis(session: Session, alert: Alert, evidence, analyzer) -> dict:
    frames = session.query(AlertFrame).filter(AlertFrame.alert_id == alert.id).all()
    jpegs = [evidence.get(frame.object_key)[0] for frame in frames]
    analysis = analyzer.analyze(alert.id, jpegs)
    alert.analysis_json = json.dumps(analysis, ensure_ascii=False)
    session.commit()
    return analysis

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts.service import rerun_analysis
from ..auth.deps import get_current_user, get_db, iso
from ..models import Alert, AlertFrame, Camera, Disposition, Room, User
from ..rooms.router import FloorPlanOut, _floor_plan

router = APIRouter(prefix="/alerts", tags=["alerts"])


class DispositionIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class DispositionOut(BaseModel):
    id: int
    note: str
    actor: str
    occurred_at: str


class FrameOut(BaseModel):
    camera_id: int
    camera_name: str
    captured_at: str


class AlertSummary(BaseModel):
    id: int
    room_id: int
    room_name: str
    alert_type: str
    started_at: str
    position: dict | None
    analysis_status: str | None
    level: str | None


class AlertDetail(BaseModel):
    id: int
    room_id: int
    room_name: str
    alert_type: str
    started_at: str
    position: dict | None
    analysis: dict | None
    observations: list
    frames: list[FrameOut]
    dispositions: list[DispositionOut]
    floor_plan: FloorPlanOut | None


def _position(raw: str | None) -> dict | None:
    return json.loads(raw) if raw else None


def _analysis(raw: str | None) -> dict | None:
    return json.loads(raw) if raw else None


def _get_alert(session: Session, alert_id: int) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="告警不存在")
    return alert


@router.get("", response_model=list[AlertSummary])
def list_alerts(
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[AlertSummary]:
    alerts = session.scalars(select(Alert).order_by(Alert.id.desc())).all()
    result = []
    for alert in alerts:
        room = session.get(Room, alert.room_id)
        analysis = _analysis(alert.analysis_json)
        result.append(
            AlertSummary(
                id=alert.id,
                room_id=alert.room_id,
                room_name=room.name if room is not None else "",
                alert_type=alert.alert_type,
                started_at=iso(alert.started_at),
                position=_position(alert.position_json),
                analysis_status=None if analysis is None else analysis.get("status"),
                level=None if analysis is None or not analysis.get("level") else analysis["level"].get("grade"),
            )
        )
    return result


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertDetail:
    alert = _get_alert(session, alert_id)
    room = session.get(Room, alert.room_id)
    frames = session.scalars(select(AlertFrame).where(AlertFrame.alert_id == alert.id)).all()
    dispositions = session.scalars(
        select(Disposition).where(Disposition.alert_id == alert.id).order_by(Disposition.id)
    ).all()
    frame_out = []
    for frame in frames:
        camera = session.get(Camera, frame.camera_id)
        frame_out.append(
            FrameOut(
                camera_id=frame.camera_id,
                camera_name=camera.name if camera is not None else str(frame.camera_id),
                captured_at=iso(frame.captured_at),
            )
        )
    return AlertDetail(
        id=alert.id,
        room_id=alert.room_id,
        room_name=room.name if room is not None else "",
        alert_type=alert.alert_type,
        started_at=iso(alert.started_at),
        position=_position(alert.position_json),
        analysis=_analysis(alert.analysis_json),
        observations=json.loads(alert.observations_json),
        frames=frame_out,
        dispositions=[
            DispositionOut(
                id=item.id,
                note=item.note,
                actor=item.actor,
                occurred_at=iso(item.occurred_at),
            )
            for item in dispositions
        ],
        floor_plan=_floor_plan(room.floor_plan_json) if room is not None else None,
    )


@router.get("/{alert_id}/frames/{camera_id}")
def alert_frame(
    alert_id: int,
    camera_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    frame = session.scalar(
        select(AlertFrame).where(
            AlertFrame.alert_id == alert_id,
            AlertFrame.camera_id == camera_id,
        )
    )
    if frame is None:
        raise HTTPException(status_code=404, detail="关键帧不存在")
    data, content_type = request.app.state.evidence.get(frame.object_key)
    return Response(content=data, media_type=content_type)


@router.post("/{alert_id}/dispositions", response_model=DispositionOut)
def add_disposition(
    alert_id: int,
    body: DispositionIn,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DispositionOut:
    _get_alert(session, alert_id)
    row = Disposition(
        alert_id=alert_id,
        note=body.note,
        actor=user.username,
        occurred_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return DispositionOut(
        id=row.id,
        note=row.note,
        actor=row.actor,
        occurred_at=iso(row.occurred_at),
    )


@router.post("/{alert_id}/analysis")
def rerun(
    alert_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    alert = _get_alert(session, alert_id)
    analyzer = request.app.state.analyzer
    if analyzer is None:
        raise HTTPException(status_code=400, detail="大模型未启用")
    return rerun_analysis(
        session,
        alert,
        request.app.state.evidence,
        analyzer,
        request.app.state.config,
        localizer=getattr(request.app.state, "localizer", None),
    )

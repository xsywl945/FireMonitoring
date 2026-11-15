from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts.query import alert_count, alert_statement
from ..alerts.report import build_alert_pdf, build_alerts_csv
from ..alerts.service import change_disposition, rerun_analysis
from ..auth.deps import get_current_user, get_db, iso
from ..models import Alert, AlertClip, AlertEvent, AlertFrame, Camera, Disposition, Room, User
from ..rooms.router import FloorPlanOut, _floor_plan

router = APIRouter(prefix="/alerts", tags=["alerts"])


class DispositionIn(BaseModel):
    action: Literal["acknowledge", "false_alarm", "close"]
    note: str = Field(default="", max_length=2000)


class DispositionOut(BaseModel):
    id: int
    action: str
    note: str
    actor: str
    occurred_at: str


class DispositionResult(BaseModel):
    status: str
    disposition: DispositionOut


class FrameOut(BaseModel):
    camera_id: int
    camera_name: str
    captured_at: str


class ClipOut(BaseModel):
    camera_id: int
    camera_name: str
    started_at: str
    ended_at: str


class AlertSummary(BaseModel):
    id: int
    room_id: int
    room_name: str
    alert_type: str
    started_at: str
    position: dict | None
    analysis_status: str | None
    level: str | None
    fire_classes: str | None
    status: str


class AlertPage(BaseModel):
    items: list[AlertSummary]
    total: int
    page: int
    page_size: int


class EventOut(BaseModel):
    id: int
    kind: str
    detail: dict
    occurred_at: str


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
    clips: list[ClipOut]
    dispositions: list[DispositionOut]
    events: list[EventOut]
    floor_plan: FloorPlanOut | None
    status: str
    level: str | None
    fire_classes: str | None


def _position(raw: str | None) -> dict | None:
    return json.loads(raw) if raw else None


def _analysis(raw: str | None) -> dict | None:
    return json.loads(raw) if raw else None


def _get_alert(session: Session, alert_id: int) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="告警不存在")
    return alert


def _summary(alert: Alert, rooms: dict[int, Room]) -> AlertSummary:
    room = rooms.get(alert.room_id)
    analysis = _analysis(alert.analysis_json)
    return AlertSummary(
        id=alert.id,
        room_id=alert.room_id,
        room_name=room.name if room is not None else "",
        alert_type=alert.alert_type,
        started_at=iso(alert.started_at),
        position=_position(alert.position_json),
        analysis_status=None if analysis is None else analysis.get("status"),
        level=alert.level,
        fire_classes=alert.fire_classes,
        status=alert.status,
    )


def _rooms(session: Session, alerts: list[Alert]) -> dict[int, Room]:
    if not alerts:
        return {}
    ids = {alert.room_id for alert in alerts}
    return {room.id: room for room in session.scalars(select(Room).where(Room.id.in_(ids)))}


def _filtered(
    *,
    room_id: int | None,
    started_from: datetime | None,
    started_to: datetime | None,
    level: str | None,
    fire_class: str | None,
    status: str | None,
):
    return alert_statement(
        room_id=room_id,
        started_from=started_from,
        started_to=started_to,
        level=level,
        fire_class=fire_class,
        status=status,
    )


@router.get("", response_model=AlertPage)
def list_alerts(
    room_id: int | None = None,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    level: str | None = None,
    fire_class: str | None = Query(default=None, pattern="^[A-F]$"),
    status: Literal["OPEN", "ACKNOWLEDGED", "FALSE_ALARM", "CLOSED"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertPage:
    stmt = _filtered(
        room_id=room_id,
        started_from=started_from,
        started_to=started_to,
        level=level,
        fire_class=fire_class,
        status=status,
    )
    total = session.scalar(
        alert_count(
            room_id=room_id,
            started_from=started_from,
            started_to=started_to,
            level=level,
            fire_class=fire_class,
            status=status,
        )
    ) or 0
    alerts = list(session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    rooms = _rooms(session, alerts)
    return AlertPage(
        items=[_summary(alert, rooms) for alert in alerts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
def export_alerts(
    room_id: int | None = None,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    level: str | None = None,
    fire_class: str | None = Query(default=None, pattern="^[A-F]$"),
    status: Literal["OPEN", "ACKNOWLEDGED", "FALSE_ALARM", "CLOSED"] | None = None,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    stmt = _filtered(
        room_id=room_id,
        started_from=started_from,
        started_to=started_to,
        level=level,
        fire_class=fire_class,
        status=status,
    )
    alerts = list(session.scalars(stmt))
    data = build_alerts_csv(session, alerts)
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=alerts.csv"},
    )


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertDetail:
    alert = _get_alert(session, alert_id)
    room = session.get(Room, alert.room_id)
    frames = session.scalars(select(AlertFrame).where(AlertFrame.alert_id == alert.id)).all()
    clips = session.scalars(select(AlertClip).where(AlertClip.alert_id == alert.id).order_by(AlertClip.camera_id)).all()
    dispositions = session.scalars(
        select(Disposition).where(Disposition.alert_id == alert.id).order_by(Disposition.id)
    ).all()
    events = session.scalars(
        select(AlertEvent).where(AlertEvent.alert_id == alert.id).order_by(AlertEvent.id)
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
    clip_out = []
    for clip in clips:
        camera = session.get(Camera, clip.camera_id)
        clip_out.append(
            ClipOut(
                camera_id=clip.camera_id,
                camera_name=camera.name if camera is not None else str(clip.camera_id),
                started_at=iso(clip.started_at),
                ended_at=iso(clip.ended_at),
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
        clips=clip_out,
        dispositions=[
            DispositionOut(
                id=item.id,
                action=item.action,
                note=item.note,
                actor=item.actor,
                occurred_at=iso(item.occurred_at),
            )
            for item in dispositions
        ],
        events=[
            EventOut(
                id=item.id,
                kind=item.kind,
                detail=json.loads(item.detail_json),
                occurred_at=iso(item.occurred_at),
            )
            for item in events
        ],
        floor_plan=_floor_plan(room.floor_plan_json) if room is not None else None,
        status=alert.status,
        level=alert.level,
        fire_classes=alert.fire_classes,
    )


@router.get("/{alert_id}/report")
def alert_report(
    alert_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    alert = _get_alert(session, alert_id)
    data = build_alert_pdf(session, request.app.state.evidence, alert)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=alert-{alert.id}.pdf"},
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


@router.get("/{alert_id}/clips/{camera_id}")
def alert_clip(
    alert_id: int,
    camera_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    clip = session.scalar(
        select(AlertClip).where(AlertClip.alert_id == alert_id, AlertClip.camera_id == camera_id)
    )
    if clip is None:
        raise HTTPException(status_code=404, detail="视频片段不存在")
    data, content_type = request.app.state.evidence.get(clip.object_key)
    return Response(content=data, media_type=content_type)


@router.post("/{alert_id}/disposition", response_model=DispositionResult)
def disposition(
    alert_id: int,
    body: DispositionIn,
    request: Request,
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DispositionResult:
    alert = _get_alert(session, alert_id)
    try:
        row, payload = change_disposition(
            session,
            alert,
            action=body.action,
            note=body.note,
            actor=user.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request.app.state.events.publish(payload)
    return DispositionResult(
        status=alert.status,
        disposition=DispositionOut(
            id=row.id,
            action=row.action,
            note=row.note,
            actor=row.actor,
            occurred_at=iso(row.occurred_at),
        ),
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

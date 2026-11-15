from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from fire_monitoring_inference.suppression.ballistics import fit_drag
from fire_monitoring_inference.suppression.calibrate import LaserSample, fit_gimbal
from fire_monitoring_inference.suppression.kinematics import GimbalParams
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user, get_db, iso, require_admin
from ..models import Alert, AlertEvent, User

router = APIRouter(prefix="/suppression", tags=["suppression"])


class AimIn(BaseModel):
    pan_cdeg: int = Field(ge=-12000, le=12000)
    tilt_cdeg: int = Field(ge=0, le=6000)


class SprayIn(BaseModel):
    room_id: int = Field(gt=0)


class SampleIn(BaseModel):
    pan_cdeg: float
    tilt_cdeg: float
    xyz: list[float] = Field(min_length=3, max_length=3)


class CalibrateIn(BaseModel):
    p0: list[float] = Field(min_length=3, max_length=3)
    yaw_deg: float = 0
    tilt_zero: float = 0
    samples: list[SampleIn] = Field(min_length=12)


class LandingIn(BaseModel):
    pitch_deg: float
    range_m: float = Field(gt=0)


class DragIn(BaseModel):
    shots: list[LandingIn] = Field(min_length=3, max_length=4)


def _service(request: Request):
    service = request.app.state.suppression
    if service is None:
        raise HTTPException(status_code=409, detail="灭火控制未启用")
    return service


def _events(session: Session, room_id: int) -> list[dict]:
    alert = session.scalar(select(Alert).where(Alert.room_id == room_id).order_by(Alert.id.desc()).limit(1))
    if alert is None:
        return []
    rows = session.scalars(
        select(AlertEvent).where(AlertEvent.alert_id == alert.id).order_by(AlertEvent.id)
    ).all()
    return [
        {
            "id": row.id,
            "alert_id": row.alert_id,
            "kind": row.kind,
            "detail": json.loads(row.detail_json),
            "occurred_at": iso(row.occurred_at),
        }
        for row in rows
    ]


@router.get("")
def suppression_status(
    request: Request,
    room_id: int | None = None,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    service = _service(request)
    body = service.snapshot(room_id)
    body["events"] = [] if room_id is None else _events(session, room_id)
    return body


@router.post("/estop")
def suppression_estop(
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict:
    return _service(request).estop()


@router.post("/unlock")
def suppression_unlock(
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    try:
        return _service(request).unlock()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/aim")
def suppression_aim(
    body: AimIn,
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    try:
        return _service(request).aim(body.pan_cdeg, body.tilt_cdeg)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/spray")
def suppression_spray(
    body: SprayIn,
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    try:
        return _service(request).manual_spray(body.room_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/calibrate")
def suppression_calibrate(
    body: CalibrateIn,
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    service = _service(request)
    initial = GimbalParams.nominal(body.p0, yaw=float(np.deg2rad(body.yaw_deg)), tilt_zero=body.tilt_zero)
    samples = [LaserSample(item.pan_cdeg, item.tilt_cdeg, np.array(item.xyz, dtype=float)) for item in body.samples]
    fitted = fit_gimbal(samples, initial)
    service.save_gimbal(fitted.params)
    return {"params": fitted.params.to_dict(), "residuals_m": fitted.residuals_m}


@router.post("/ballistics")
def suppression_ballistics(
    body: DragIn,
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    service = _service(request)
    fitted = fit_drag([(np.deg2rad(item.pitch_deg), item.range_m) for item in body.shots])
    service.save_drag(fitted.speed, fitted.drag)
    return {"speed": fitted.speed, "drag": fitted.drag}

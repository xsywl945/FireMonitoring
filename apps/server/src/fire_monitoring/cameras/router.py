from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user, get_db, require_admin
from ..config import AppConfig
from ..models import Camera, User

router = APIRouter(prefix="/cameras", tags=["cameras"])


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_type: str = Field(pattern="^(USB|RTSP)$")
    source_uri: str = Field(min_length=1, max_length=1000)
    stream_key: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=100)
    target_fps: float | None = Field(default=None, gt=0, le=60)


class Landmark(BaseModel):
    world_m: tuple[float, float, float]
    pixel: tuple[float, float]


class CalibrationIn(BaseModel):
    intrinsics: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    distortion: tuple[float, float, float, float, float]
    landmarks: list[Landmark] = Field(min_length=4)


class CameraOut(BaseModel):
    id: int
    name: str
    source_type: str
    source_uri: str
    stream_key: str
    target_fps: float
    calibration: dict | None


def camera_out(camera: Camera) -> CameraOut:
    calibration = json.loads(camera.calibration_json) if camera.calibration_json else None
    return CameraOut(
        id=camera.id,
        name=camera.name,
        source_type=camera.source_type,
        source_uri=camera.source_uri,
        stream_key=camera.stream_key,
        target_fps=camera.target_fps,
        calibration=calibration,
    )


def _get_camera(session: Session, camera_id: int) -> Camera:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="摄像头不存在")
    return camera


@router.get("", response_model=list[CameraOut])
def list_cameras(
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[CameraOut]:
    cameras = session.scalars(select(Camera).order_by(Camera.id)).all()
    return [camera_out(camera) for camera in cameras]


@router.post("", response_model=CameraOut)
def create_camera(
    body: CameraIn,
    request: Request,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> CameraOut:
    exists = session.scalar(select(Camera).where(Camera.stream_key == body.stream_key))
    if exists is not None:
        raise HTTPException(status_code=409, detail="流标识已存在")
    config: AppConfig = request.app.state.config
    camera = Camera(
        name=body.name,
        source_type=body.source_type,
        source_uri=body.source_uri,
        stream_key=body.stream_key,
        target_fps=body.target_fps if body.target_fps is not None else config.cameras.default_fps,
        created_at=datetime.now(UTC),
    )
    session.add(camera)
    session.commit()
    return camera_out(camera)


@router.put("/{camera_id}", response_model=CameraOut)
def update_camera(
    camera_id: int,
    body: CameraIn,
    request: Request,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> CameraOut:
    camera = _get_camera(session, camera_id)
    exists = session.scalar(
        select(Camera).where(Camera.stream_key == body.stream_key, Camera.id != camera_id)
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="流标识已存在")
    config: AppConfig = request.app.state.config
    camera.name = body.name
    camera.source_type = body.source_type
    camera.source_uri = body.source_uri
    camera.stream_key = body.stream_key
    camera.target_fps = (
        body.target_fps if body.target_fps is not None else config.cameras.default_fps
    )
    session.commit()
    return camera_out(camera)


@router.delete("/{camera_id}")
def delete_camera(
    camera_id: int,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    camera = _get_camera(session, camera_id)
    session.delete(camera)
    session.commit()
    return {"ok": True}


@router.put("/{camera_id}/calibration", response_model=CameraOut)
def save_calibration(
    camera_id: int,
    body: CalibrationIn,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> CameraOut:
    camera = _get_camera(session, camera_id)
    camera.calibration_json = body.model_dump_json()
    session.commit()
    return camera_out(camera)

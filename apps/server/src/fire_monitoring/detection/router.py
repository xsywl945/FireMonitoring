from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user, get_db
from ..models import Camera, Room, RoomCamera, User

router = APIRouter(tags=["detection"])


@router.get("/health")
def health(request: Request) -> dict:
    worker = request.app.state.worker
    if worker is not None and worker.failed:
        raise HTTPException(status_code=503, detail="detection stopped")
    return {"detection": "running" if worker is not None and worker.alive else "off"}


class DetectionBox(BaseModel):
    class_name: str
    confidence: float
    bbox: list[float]


class LiveCamera(BaseModel):
    camera_id: int
    slot: int
    name: str
    whep_url: str
    online: bool
    width: int
    height: int
    states: dict[str, str]
    detections: list[DetectionBox]


class LiveOut(BaseModel):
    room_id: int
    cameras: list[LiveCamera]


@router.get("/rooms/{room_id}/live", response_model=LiveOut)
def live(
    room_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> LiveOut:
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="教室不存在")
    bindings = session.scalars(
        select(RoomCamera).where(RoomCamera.room_id == room_id).order_by(RoomCamera.slot)
    ).all()
    whep_base = request.app.state.config.mediamtx.whep_base.rstrip("/")
    cameras: list[LiveCamera] = []
    for binding in bindings:
        camera = session.get(Camera, binding.camera_id)
        if camera is None:
            continue
        snap = request.app.state.live.get(camera.id)
        cameras.append(
            LiveCamera(
                camera_id=camera.id,
                slot=binding.slot,
                name=camera.name,
                whep_url=f"{whep_base}/{camera.stream_key}/whep",
                online=snap["online"],
                width=snap["width"],
                height=snap["height"],
                states=snap["states"],
                detections=[DetectionBox(**item) for item in snap["detections"]],
            )
        )
    return LiveOut(room_id=room_id, cameras=cameras)

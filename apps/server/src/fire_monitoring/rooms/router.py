from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fire_monitoring_inference.analysis.rules import SCENE_TYPES
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user, get_db, require_admin
from ..calibration.service import ready
from ..models import Camera, Room, RoomCamera, User

router = APIRouter(prefix="/rooms", tags=["rooms"])

SCENE_PATTERN = "^(" + "|".join(SCENE_TYPES) + ")$"


class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scene_type: str = Field(pattern=SCENE_PATTERN)


class BindingIn(BaseModel):
    camera_ids: list[int | None] = Field(min_length=4, max_length=4)


class BoundCamera(BaseModel):
    camera_id: int
    slot: int
    name: str
    stream_key: str
    source_type: str
    calibrated: bool


class FloorPlanOut(BaseModel):
    origin_px: list[float]
    meters_per_pixel: float
    origin_world_m: list[float]
    content_type: str
    combustibles: list[dict]


class RoomOut(BaseModel):
    id: int
    name: str
    scene_type: str
    cameras: list[BoundCamera]
    floor_plan: FloorPlanOut | None


def _floor_plan(raw: str | None) -> FloorPlanOut | None:
    if not raw:
        return None
    data = json.loads(raw)
    return FloorPlanOut(
        origin_px=data["origin_px"],
        meters_per_pixel=data["meters_per_pixel"],
        origin_world_m=data["origin_world_m"],
        content_type=data["content_type"],
        combustibles=data.get("combustibles", []),
    )


def _room_out(session: Session, room: Room) -> RoomOut:
    bindings = session.scalars(
        select(RoomCamera).where(RoomCamera.room_id == room.id).order_by(RoomCamera.slot)
    ).all()
    cameras: list[BoundCamera] = []
    for binding in bindings:
        camera = session.get(Camera, binding.camera_id)
        if camera is None:
            continue
        cameras.append(
            BoundCamera(
                camera_id=camera.id,
                slot=binding.slot,
                name=camera.name,
                stream_key=camera.stream_key,
                source_type=camera.source_type,
                calibrated=ready(camera.calibration_json),
            )
        )
    return RoomOut(
        id=room.id,
        name=room.name,
        scene_type=room.scene_type,
        cameras=cameras,
        floor_plan=_floor_plan(room.floor_plan_json),
    )


def _get_room(session: Session, room_id: int) -> Room:
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="教室不存在")
    return room


@router.get("", response_model=list[RoomOut])
def list_rooms(
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RoomOut]:
    rooms = session.scalars(select(Room).order_by(Room.id)).all()
    return [_room_out(session, room) for room in rooms]


@router.post("", response_model=RoomOut)
def create_room(
    body: RoomIn,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoomOut:
    exists = session.scalar(select(Room).where(Room.name == body.name))
    if exists is not None:
        raise HTTPException(status_code=409, detail="教室名称已存在")
    room = Room(name=body.name, scene_type=body.scene_type, created_at=datetime.now(UTC))
    session.add(room)
    session.commit()
    return _room_out(session, room)


@router.get("/{room_id}", response_model=RoomOut)
def get_room(
    room_id: int,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RoomOut:
    return _room_out(session, _get_room(session, room_id))


@router.put("/{room_id}", response_model=RoomOut)
def update_room(
    room_id: int,
    body: RoomIn,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoomOut:
    room = _get_room(session, room_id)
    exists = session.scalar(select(Room).where(Room.name == body.name, Room.id != room_id))
    if exists is not None:
        raise HTTPException(status_code=409, detail="教室名称已存在")
    room.name = body.name
    room.scene_type = body.scene_type
    session.commit()
    return _room_out(session, room)


@router.delete("/{room_id}")
def delete_room(
    room_id: int,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    room = _get_room(session, room_id)
    session.delete(room)
    session.commit()
    return {"ok": True}


@router.put("/{room_id}/cameras", response_model=RoomOut)
def replace_bindings(
    room_id: int,
    body: BindingIn,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoomOut:
    room = _get_room(session, room_id)
    chosen = [camera_id for camera_id in body.camera_ids if camera_id is not None]
    if len(chosen) != len(set(chosen)):
        raise HTTPException(status_code=400, detail="同一摄像头不能重复绑定")
    for camera_id in chosen:
        camera = session.get(Camera, camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="摄像头不存在")
        other = session.scalar(
            select(RoomCamera).where(
                RoomCamera.camera_id == camera_id,
                RoomCamera.room_id != room_id,
            )
        )
        if other is not None:
            raise HTTPException(status_code=409, detail="摄像头已绑定到其他教室")
    session.execute(delete(RoomCamera).where(RoomCamera.room_id == room_id))
    for slot, camera_id in enumerate(body.camera_ids, start=1):
        if camera_id is None:
            continue
        session.add(RoomCamera(room_id=room.id, camera_id=camera_id, slot=slot))
    session.commit()
    return _room_out(session, room)


@router.post("/{room_id}/floor-plan", response_model=RoomOut)
def upload_floor_plan(
    room_id: int,
    request: Request,
    file: UploadFile,
    origin_x: float = Form(),
    origin_y: float = Form(),
    meters_per_pixel: float = Form(),
    world_x: float = Form(),
    world_y: float = Form(),
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoomOut:
    if meters_per_pixel <= 0:
        raise HTTPException(status_code=400, detail="比例必须大于 0")
    room = _get_room(session, room_id)
    data = file.file.read()
    content_type = file.content_type or "application/octet-stream"
    key = f"floor-plans/{room.id}"
    request.app.state.evidence.put(key, data, content_type)
    room.floor_plan_json = json.dumps(
        {
            "object_key": key,
            "content_type": content_type,
            "origin_px": [origin_x, origin_y],
            "meters_per_pixel": meters_per_pixel,
            "origin_world_m": [world_x, world_y],
        }
    )
    session.commit()
    return _room_out(session, room)


class RegionIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    polygon: list[list[float]] = Field(min_length=3)


class RegionsIn(BaseModel):
    regions: list[RegionIn]


@router.put("/{room_id}/combustibles", response_model=RoomOut)
def replace_combustibles(
    room_id: int,
    body: RegionsIn,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RoomOut:
    room = _get_room(session, room_id)
    if not room.floor_plan_json:
        raise HTTPException(status_code=400, detail="未上传平面图")
    for region in body.regions:
        if any(len(point) != 2 for point in region.polygon):
            raise HTTPException(status_code=400, detail="区域顶点必须是平面坐标")
    meta = json.loads(room.floor_plan_json)
    meta["combustibles"] = [
        {"name": region.name, "polygon": region.polygon} for region in body.regions
    ]
    room.floor_plan_json = json.dumps(meta)
    session.commit()
    return _room_out(session, room)


@router.get("/{room_id}/floor-plan")
def floor_plan_image(
    room_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    room = _get_room(session, room_id)
    if not room.floor_plan_json:
        raise HTTPException(status_code=404, detail="未上传平面图")
    meta = json.loads(room.floor_plan_json)
    data, content_type = request.app.state.evidence.get(meta["object_key"])
    return Response(content=data, media_type=content_type)

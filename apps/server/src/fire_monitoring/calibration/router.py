from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user, get_db, require_admin
from ..cameras.router import CameraOut, camera_out
from ..models import User
from .extrinsics import detect_control_points
from .pdf import charuco_pdf, marker_pdf
from .service import decode_image, write_extrinsics, write_intrinsics

router = APIRouter(tags=["calibration"])


class DetectedMarker(BaseModel):
    marker_id: int
    pixel: tuple[float, float]


class DetectOut(BaseModel):
    markers: list[DetectedMarker]


class ControlPointIn(BaseModel):
    marker_id: int
    world_m: tuple[float, float, float]


def _value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _pdf(name: str, payload: bytes) -> Response:
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/calibration/boards/charuco")
def download_charuco(
    paper: str,
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        payload = charuco_pdf(paper)
    except ValueError as exc:
        raise _value_error(exc) from exc
    return _pdf(f"charuco-{paper}.pdf", payload)


@router.get("/calibration/boards/markers")
def download_markers(
    paper: str,
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        payload = marker_pdf(paper)
    except ValueError as exc:
        raise _value_error(exc) from exc
    return _pdf(f"markers-{paper}.pdf", payload)


@router.post("/cameras/{camera_id}/calibration/intrinsics", response_model=CameraOut)
async def calibrate_intrinsics(
    camera_id: int,
    paper: str = Form(),
    files: list[UploadFile] = File(),
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> CameraOut:
    from ..cameras.router import _get_camera

    camera = _get_camera(session, camera_id)
    images = [decode_image(await item.read()) for item in files]
    try:
        write_intrinsics(camera, images, paper)
    except ValueError as exc:
        raise _value_error(exc) from exc
    session.commit()
    return camera_out(camera)


@router.post("/cameras/{camera_id}/calibration/detect", response_model=DetectOut)
async def detect_markers(
    camera_id: int,
    file: UploadFile = File(),
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> DetectOut:
    from ..cameras.router import _get_camera

    _get_camera(session, camera_id)
    image = decode_image(await file.read())
    try:
        found = detect_control_points(image)
    except ValueError as exc:
        raise _value_error(exc) from exc
    return DetectOut(markers=[DetectedMarker(**item) for item in found])


@router.post("/cameras/{camera_id}/calibration/extrinsics", response_model=CameraOut)
async def calibrate_extrinsics(
    camera_id: int,
    request: Request,
    file: UploadFile = File(),
    points: str = Form(),
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> CameraOut:
    from ..cameras.router import _get_camera

    camera = _get_camera(session, camera_id)
    try:
        payload = json.loads(points)
        parsed = [ControlPointIn.model_validate(item) for item in payload]
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="控制点表格无法解析") from exc
    if len(parsed) < 4:
        raise HTTPException(status_code=400, detail="至少需要 4 个控制点")
    worlds = {item.marker_id: item.world_m for item in parsed}
    if len(worlds) != len(parsed):
        raise HTTPException(status_code=400, detail="控制点编号重复")
    image = decode_image(await file.read())
    sigma = request.app.state.config.localization.landmark_sigma_px
    try:
        write_extrinsics(camera, image, worlds, sigma)
    except ValueError as exc:
        raise _value_error(exc) from exc
    session.commit()
    return camera_out(camera)


@router.get("/cameras/{camera_id}/frame")
def grab_frame(
    camera_id: int,
    request: Request,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    from ..cameras.router import _get_camera

    _get_camera(session, camera_id)
    worker = request.app.state.worker
    if worker is None:
        raise HTTPException(status_code=409, detail="检测未运行")
    try:
        payload = worker.latest_png(camera_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(content=payload, media_type="image/png")

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..auth.deps import get_current_user, require_admin
from ..models import User

router = APIRouter(prefix="/demo", tags=["demo"])


class StartIn(BaseModel):
    script: str = Field(min_length=1)
    speed: float = Field(default=1, ge=0, le=60)


def _demo(request: Request):
    demo = request.app.state.demo
    if demo is None:
        raise HTTPException(status_code=409, detail="演示模式没有打开")
    return demo


@router.get("/mode")
def demo_mode(request: Request) -> dict:
    demo = request.app.state.demo
    if demo is None:
        return {"enabled": False, "label": "演示模式"}
    return {
        "enabled": True,
        "label": "演示模式",
        "synthetic": bool(demo.pack.get("synthetic")),
        "note": demo.pack.get("note", ""),
    }


@router.get("")
def demo_status(request: Request, _user: User = Depends(get_current_user)) -> dict:
    return _demo(request).status()


@router.post("/start")
def demo_start(
    body: StartIn,
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    demo = _demo(request)
    try:
        demo.player.start(body.script, body.speed)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return demo.status()


@router.post("/reset")
def demo_reset(request: Request, _admin: User = Depends(require_admin)) -> dict:
    demo = _demo(request)
    demo.player.stop()
    demo.prepare_script(None)
    demo.player.script_id = None
    demo.player.finished = False
    demo.player.error = None
    demo.player.running = False
    return demo.status()


@router.get("/frames/{camera_id}")
def demo_frame(
    camera_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        payload = _demo(request).frame(camera_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=payload, media_type="image/jpeg")

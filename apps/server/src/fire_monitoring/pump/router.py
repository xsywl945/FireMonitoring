from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth.deps import get_current_user
from ..models import User

router = APIRouter(prefix="/pump", tags=["pump"])


def _disabled() -> dict:
    return {
        "enabled": False,
        "zoneId": None,
        "connected": False,
        "deviceState": "DISABLED",
        "inhibited": False,
        "lastError": None,
        "records": [],
    }


@router.get("")
def pump_status(request: Request, _user: User = Depends(get_current_user)) -> dict:
    pump = request.app.state.pump
    if pump is None:
        return _disabled()
    return pump.snapshot()


@router.post("/stop")
def pump_stop(request: Request, _user: User = Depends(get_current_user)) -> dict:
    pump = request.app.state.pump
    if pump is None:
        return _disabled()
    return pump.emergency_stop()

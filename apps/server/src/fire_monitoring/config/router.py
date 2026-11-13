from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth.deps import require_admin
from ..config import masked_config
from ..models import User

router = APIRouter(tags=["config"])


@router.get("/config")
def current_config(request: Request, _admin: User = Depends(require_admin)) -> dict:
    return masked_config(request.app.state.config)

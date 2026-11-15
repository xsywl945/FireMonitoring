from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from ..auth.deps import require_admin
from ..config import apply_public_update, public_config
from ..config.model import AppConfig
from ..models import User

router = APIRouter(tags=["config"])


@router.get("/config")
def current_config(request: Request, _admin: User = Depends(require_admin)) -> dict:
    return public_config(request.app.state.config)


@router.put("/config")
def update_config(
    body: dict,
    request: Request,
    _admin: User = Depends(require_admin),
) -> dict:
    path: Path = request.app.state.config_path
    current = json.loads(path.read_text(encoding="utf-8"))
    try:
        merged = apply_public_update(current, body)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"restart_required": True, "config": public_config(AppConfig.model_validate(merged))}

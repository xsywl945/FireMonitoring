from __future__ import annotations

import jwt
from fastapi import APIRouter, WebSocket
from sqlalchemy.orm import Session

from ..models import User

router = APIRouter(tags=["events"])


def _user(session: Session, secret: str, token: str) -> User | None:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
    return session.get(User, user_id)


@router.websocket("/events")
async def events(websocket: WebSocket) -> None:
    await websocket.accept()
    session = websocket.app.state.session_factory()
    try:
        user = _user(
            session,
            websocket.app.state.config.auth.jwt_secret,
            websocket.query_params.get("token", ""),
        )
    finally:
        session.close()
    if user is None:
        await websocket.close(code=1008)
        return
    hub = websocket.app.state.events
    queue = hub.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    finally:
        hub.unsubscribe(queue)

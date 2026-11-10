from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..models import User


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    request: Request,
    authorization: str = Header(),
    session: Session = Depends(get_db),
) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(
            token, request.app.state.config.auth.jwt_secret, algorithms=["HS256"]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="未登录") from exc
    user = session.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from .deps import get_current_user, get_db, require_admin
from .security import hash_password, issue_token, password_matches

router = APIRouter(tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str


class LoginOut(BaseModel):
    access_token: str
    user: UserOut


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginBody, request: Request, session: Session = Depends(get_db)) -> LoginOut:
    user = session.scalar(select(User).where(User.username == body.username))
    if user is None or not password_matches(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = issue_token(user, request.app.state.config)
    return LoginOut(access_token=token, user=user_out(user))


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return user_out(user)


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "operator"]


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["admin", "operator"] | None = None
    password: str | None = Field(default=None, min_length=1)


@router.get("/users", response_model=list[UserOut])
def list_users(
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[UserOut]:
    users = session.scalars(select(User).order_by(User.id)).all()
    return [user_out(user) for user in users]


@router.post("/users", response_model=UserOut)
def create_user(
    body: UserIn,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> UserOut:
    exists = session.scalar(select(User).where(User.username == body.username))
    if exists is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
        created_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserPatch,
    session: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> UserOut:
    if body.display_name is None and body.role is None and body.password is None:
        raise HTTPException(status_code=400, detail="没有要修改的内容")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = body.role
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    session.commit()
    return user_out(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    session: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="不能删除当前登录账号")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    session.delete(user)
    session.commit()
    return {"ok": True}

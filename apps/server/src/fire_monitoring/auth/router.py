from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from .deps import get_current_user, get_db
from .security import issue_token, password_matches

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

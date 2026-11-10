from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import AppConfig
from ..models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def password_matches(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def issue_token(user: User, config: AppConfig) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(UTC) + timedelta(seconds=config.auth.jwt_expiration_seconds),
    }
    return jwt.encode(payload, config.auth.jwt_secret, algorithm="HS256")


def seed_users(session: Session, config: AppConfig) -> None:
    now = datetime.now(UTC)
    for item in config.auth.users:
        user = session.scalar(select(User).where(User.username == item.username))
        hashed = hash_password(item.password)
        if user is None:
            session.add(
                User(
                    username=item.username,
                    display_name=item.display_name,
                    password_hash=hashed,
                    role=item.role,
                    created_at=now,
                )
            )
        else:
            user.display_name = item.display_name
            user.password_hash = hashed
            user.role = item.role
    session.commit()

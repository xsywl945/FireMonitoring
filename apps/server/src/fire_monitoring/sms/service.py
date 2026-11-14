from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import AppConfig
from ..models import SmsDispatch


class SmsService:
    def __init__(self, config: AppConfig, sender) -> None:
        self.config = config
        self.sender = sender

    def notify(
        self,
        session: Session,
        *,
        room_id: int,
        room_name: str,
        level: str,
        method: str,
        when: datetime,
    ) -> bool:
        settings = self.config.sms
        if not settings.enabled or not settings.recipients:
            return False
        last = session.scalar(
            select(SmsDispatch)
            .where(SmsDispatch.room_id == room_id)
            .order_by(SmsDispatch.id.desc())
        )
        if last is not None:
            sent_at = last.sent_at
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=when.tzinfo)
            if (when - sent_at).total_seconds() < settings.cooldown_seconds:
                return False
        params = {"location": room_name, "level": level, "method": method}
        for phone in settings.recipients:
            self.sender.send(phone, params)
        session.add(SmsDispatch(room_id=room_id, sent_at=when))
        return True

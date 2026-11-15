from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select

from ..models import Alert


def alert_filters(
    *,
    room_id: int | None,
    started_from: datetime | None,
    started_to: datetime | None,
    level: str | None,
    fire_class: str | None,
    status: str | None,
) -> list:
    filters = []
    if room_id is not None:
        filters.append(Alert.room_id == room_id)
    if started_from is not None:
        filters.append(Alert.started_at >= started_from)
    if started_to is not None:
        filters.append(Alert.started_at <= started_to)
    if level is not None:
        filters.append(Alert.level == level)
    if status is not None:
        filters.append(Alert.status == status)
    if fire_class is not None:
        filters.append(Alert.fire_classes.like(f"%{fire_class}%"))
    return filters


def alert_statement(**kwargs) -> Select:
    return select(Alert).where(*alert_filters(**kwargs)).order_by(Alert.started_at.desc(), Alert.id.desc())


def alert_count(**kwargs) -> Select:
    from sqlalchemy import func

    return select(func.count()).select_from(Alert).where(*alert_filters(**kwargs))

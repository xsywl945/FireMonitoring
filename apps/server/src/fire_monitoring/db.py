from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import AppConfig


class Base(DeclarativeBase):
    pass


def mysql_url(config: AppConfig) -> str:
    database = config.database
    user = quote_plus(database.user)
    password = quote_plus(database.password)
    return (
        f"mysql+pymysql://{user}:{password}@{database.host}:{database.port}/"
        f"{database.name}?charset=utf8mb4"
    )


def make_engine(url: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(factory) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    finally:
        session.close()

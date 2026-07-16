from __future__ import annotations

import json
import threading
from typing import Protocol

from .contracts import EventEnvelope


class EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> str:
        """Publish an event and return the broker or local message identifier."""

    def health(self) -> bool:
        """Return whether the publisher's backing service is reachable."""


class MemoryEventPublisher:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []
        self._lock = threading.Lock()

    def publish(self, event: EventEnvelope) -> str:
        with self._lock:
            self.events.append(event)
            return str(len(self.events))

    def health(self) -> bool:
        return True


class StdoutEventPublisher:
    def publish(self, event: EventEnvelope) -> str:
        print(json.dumps(event.to_wire(), ensure_ascii=False, separators=(",", ":")))
        return str(event.event_id)

    def health(self) -> bool:
        return True


class RedisStreamPublisher:
    """Redis Streams publisher using one JSON envelope per XADD entry."""

    def __init__(
        self,
        redis_url: str,
        *,
        stream: str = "monitoring.events",
        maxlen: int = 50_000,
        client: object | None = None,
    ) -> None:
        if client is None:
            try:
                import redis
            except ImportError as exc:  # pragma: no cover - dependency error path
                raise RuntimeError("install the redis package to use RedisStreamPublisher") from exc
            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        self._client = client
        self.stream = stream
        self.maxlen = maxlen

    def publish(self, event: EventEnvelope) -> str:
        body = json.dumps(event.to_wire(), ensure_ascii=False, separators=(",", ":"))
        message_id = self._client.xadd(  # type: ignore[attr-defined]
            self.stream,
            {"event": body},
            maxlen=self.maxlen,
            approximate=True,
        )
        return str(message_id)

    def health(self) -> bool:
        try:
            return bool(self._client.ping())  # type: ignore[attr-defined]
        except Exception:
            return False

from __future__ import annotations

import asyncio
import threading


class EventHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self.published: list[dict] = []

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._queues.discard(queue)

    def publish(self, payload: dict) -> None:
        self.published.append(payload)
        loop = self._loop
        if loop is None:
            return
        with self._lock:
            queues = list(self._queues)
        for queue in queues:
            loop.call_soon_threadsafe(queue.put_nowait, payload)

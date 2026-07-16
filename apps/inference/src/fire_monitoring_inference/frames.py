from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FramePacket:
    camera_id: int
    captured_at: datetime
    monotonic_ns: int
    image: Any
    width: int
    height: int


class LatestFrameQueue(Generic[T]):
    """A bounded queue that drops the oldest frame instead of accumulating latency."""

    def __init__(self, capacity: int = 2) -> None:
        if capacity < 1 or capacity > 3:
            raise ValueError("frame queue capacity must be between 1 and 3")
        self._items: deque[T] = deque(maxlen=capacity)
        self._condition = threading.Condition()
        self._dropped = 0

    @property
    def capacity(self) -> int:
        return self._items.maxlen or 0

    @property
    def dropped_count(self) -> int:
        with self._condition:
            return self._dropped

    def put(self, item: T) -> None:
        with self._condition:
            if len(self._items) == self.capacity:
                self._dropped += 1
            self._items.append(item)
            self._condition.notify()

    def get_latest(self, timeout: float | None = None) -> T | None:
        """Return the newest item and discard any older waiting items."""
        with self._condition:
            if not self._items and not self._condition.wait_for(lambda: self._items, timeout):
                return None
            item = self._items[-1]
            self._dropped += max(0, len(self._items) - 1)
            self._items.clear()
            return item

    def __len__(self) -> int:
        with self._condition:
            return len(self._items)

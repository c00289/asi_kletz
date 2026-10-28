"""EventBus: every state change is published here so front ends can refresh live."""

from __future__ import annotations

import datetime as dt
from collections import deque
from collections.abc import Callable
from typing import Any

Handler = Callable[[str, dict[str, Any]], None]


class EventBus:
    """Publish / subscribe with a bounded history. Every event carries ``seq`` (1, 2, 3, ...), one
    counter per bus, so a poller (``GET /events?since=<n>`` on the automation server) can ask for
    what it has not seen; ``seq`` is the latest number and ``since`` the events after one."""

    def __init__(self, history: int = 500) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=history)
        self.seq = 0

    def subscribe(self, topic: str, handler: Handler) -> Handler:
        """Subscribe to an exact topic such as ``entity.created``, or ``*`` for everything."""
        self._handlers.setdefault(topic, []).append(handler)
        return handler

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        if topic in self._handlers and handler in self._handlers[topic]:
            self._handlers[topic].remove(handler)

    def publish(self, topic: str, **payload: Any) -> None:
        self.seq += 1
        event = {
            "topic": topic,
            "ts": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "seq": self.seq,
            **payload,
        }
        self.history.append(event)
        for handler in (*self._handlers.get(topic, ()), *self._handlers.get("*", ())):
            handler(topic, event)

    def last(self, n: int = 10) -> list[dict[str, Any]]:
        return list(self.history)[-n:]

    def oldest_seq(self) -> int | None:
        """The ``seq`` of the oldest event still in the history; ``None`` when it is empty."""
        return int(self.history[0]["seq"]) if self.history else None

    def since(self, n: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        """The events with ``seq > n``, oldest first, at most ``limit`` of them."""
        return [event for event in self.history if event["seq"] > n][: max(0, limit)]

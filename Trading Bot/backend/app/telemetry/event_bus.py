import asyncio
import threading
from collections import deque
from typing import Any


class EventBus:
    """Small process-local event bus used by the dashboard WebSocket.

    The trading engine can publish the same JSON-safe event shape from any
    cycle. Subscribers receive a bounded history first, then live events.
    """

    def __init__(self, max_history: int = 250):
        self.history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self.subscribers: set[tuple[asyncio.AbstractEventLoop,asyncio.Queue]] = set()
        self.lock = threading.RLock()

    @staticmethod
    def _deliver(queue, item):
        if queue.full(): queue.get_nowait()
        queue.put_nowait(item)

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.history.append(event)
            subscribers=list(self.subscribers)
        for loop,queue in subscribers:
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._deliver,queue,event)
        return event

    def recent(self, limit: int = 80) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.history)[-limit:]

    async def subscribe(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        subscriber=(asyncio.get_running_loop(),queue)
        with self.lock:
            self.subscribers.add(subscriber)
        try:
            for event in self.recent(80):
                yield event
            while True:
                yield await queue.get()
        finally:
            with self.lock:
                self.subscribers.discard(subscriber)


event_bus = EventBus()

from __future__ import annotations

import asyncio
import json
from typing import Any


class InMemoryQueue:
    def __init__(self, name: str) -> None:
        self.name = name
        self._q: asyncio.Queue[str] = asyncio.Queue()

    async def push(self, payload: dict[str, Any]) -> None:
        await self._q.put(json.dumps(payload))

    async def pop(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            if timeout:
                raw = await asyncio.wait_for(self._q.get(), timeout=timeout)
            else:
                raw = await self._q.get()
            return json.loads(raw)
        except TimeoutError:
            return None


def get_queue(name: str) -> InMemoryQueue:
    # For MVP, return a per-process in-memory queue. Swap with Redis later.
    global _QUEUES
    q = _QUEUES.get(name)
    if not q:
        q = InMemoryQueue(name)
        _QUEUES[name] = q
    return q


_QUEUES: dict[str, InMemoryQueue] = {}

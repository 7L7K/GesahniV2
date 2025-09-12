from __future__ import annotations

import time

# Simple in-memory pending confirmation queue (durable store advisable)
_PENDING: dict[str, dict] = {}


def enqueue(key: str, payload: dict, ttl: int = 30) -> None:
    _PENDING[key] = {"payload": payload, "expires": time.time() + ttl}


def dequeue(key: str) -> dict | None:
    item = _PENDING.pop(key, None)
    if not item:
        return None
    if time.time() > item["expires"]:
        return None
    return item["payload"]


def cleanup() -> None:
    now = time.time()
    for k in list(_PENDING.keys()):
        if _PENDING[k]["expires"] < now:
            _PENDING.pop(k, None)





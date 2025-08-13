from __future__ import annotations

import asyncio
from typing import Dict, Set

from fastapi import APIRouter, Depends, WebSocket

from ..deps.user import get_current_user_id
from ..security import verify_ws


router = APIRouter(tags=["care"], dependencies=[])


_topics: Dict[str, Set[WebSocket]] = {}
_lock = asyncio.Lock()


async def _broadcast(topic: str, payload: dict) -> None:
    async with _lock:
        clients = set(_topics.get(topic) or set())
    if not clients:
        return
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json({"topic": topic, "data": payload})
        except Exception:
            dead.append(ws)
    if dead:
        async with _lock:
            for ws in dead:
                try:
                    for t in list(_topics.keys()):
                        _topics[t].discard(ws)
                    await ws.close()
                except Exception:
                    pass


@router.websocket("/ws/care")
async def ws_care(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    await verify_ws(ws)
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            # {action: 'subscribe', topic: 'resident:r1'}
            if isinstance(msg, dict) and msg.get("action") == "subscribe":
                topic = str(msg.get("topic") or "").strip()
                if topic:
                    async with _lock:
                        _topics.setdefault(topic, set()).add(ws)
            # ping
            if msg == "ping" or (isinstance(msg, dict) and msg.get("action") == "ping"):
                await ws.send_text("pong")
    except Exception:
        pass
    finally:
        async with _lock:
            for t in list(_topics.keys()):
                _topics[t].discard(ws)


async def broadcast_resident(resident_id: str, event: str, data: dict) -> None:
    topic = f"resident:{resident_id}"
    await _broadcast(topic, {"event": event, **data})



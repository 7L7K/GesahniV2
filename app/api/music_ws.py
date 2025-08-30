from __future__ import annotations

import logging
import os
import time as _t
from typing import Any

from fastapi import APIRouter, Depends, WebSocket

from app.deps.user import get_current_user_id
from app.security import verify_ws
from .music_http import _build_state_payload


router = APIRouter(tags=["Music"])  # mounted under /v1


_ws_clients: set[WebSocket] = set()


def _ws_origin_allowed(ws: WebSocket) -> bool:
    try:
        origin = ws.headers.get("Origin")
        configured = list(getattr(ws.app.state, "allowed_origins", []))  # type: ignore[attr-defined]
        if not configured:
            _env = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000") or "http://localhost:3000"
            configured = [o.strip() for o in _env.split(",") if o.strip()]
        return (not origin) or (origin in configured)
    except Exception:
        return True


async def _broadcast(topic: str, payload: dict) -> None:
    if not _ws_clients:
        return
    import asyncio as _aio
    dead: list[WebSocket] = []
    sem = _aio.Semaphore(int(os.getenv("WS_BROADCAST_CONCURRENCY", "64") or 64))

    async def _send(ws: WebSocket) -> None:
        try:
            async with sem:
                await ws.send_json({"topic": topic, "data": payload})
        except Exception:
            dead.append(ws)

    await _aio.gather(*[_send(ws) for ws in list(_ws_clients)], return_exceptions=True)
    for ws in dead:
        try:
            _ws_clients.discard(ws)
            await ws.close()
        except Exception:
            pass


@router.websocket("/ws/music")
async def ws_music(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    if not _ws_origin_allowed(ws):
        try:
            await ws.close(code=1008, reason="origin_not_allowed")
        except Exception:
            pass
        return

    await verify_ws(ws)
    try:
        hdr = ws.headers.get("Authorization") or ""
        has_authz = hdr.lower().startswith("bearer ")
        uid = getattr(ws.state, "user_id", None)
        outage = getattr(ws.state, "session_store_unavailable", False)
        if outage and (not has_authz) and (not uid):
            try:
                await ws.close(code=1013, reason="identity_unavailable")
            except Exception:
                pass
            return
    except Exception:
        pass
    try:
        require_jwt = os.getenv("REQUIRE_JWT", "0").strip().lower() in {"1", "true", "yes", "on"}
        uid = getattr(ws.state, "user_id", None)
        if require_jwt and not uid:
            try:
                await ws.close(code=1008)
            except Exception:
                pass
            return
    except Exception:
        pass

    try:
        await ws.accept(subprotocol="json.realtime.v1")
    except Exception:
        await ws.accept()
    _ws_clients.add(ws)
    _logger = logging.getLogger(__name__)
    connected_at = _t.time()
    last_pong = _t.monotonic()
    try:
        _logger.info("ws.music.accept", extra={"meta": {"user_id": getattr(ws.state, "user_id", None)}})
    except Exception:
        pass
    try:
        while True:
            import asyncio as _aio
            recv_task = _aio.create_task(ws.receive())
            done, _ = await _aio.wait({recv_task}, timeout=25.0)
            if not done:
                # cancel the pending receive to avoid task leak
                recv_task.cancel()
                try:
                    await recv_task
                except _aio.CancelledError:
                    pass
                try:
                    await ws.send_text("ping")
                except Exception:
                    break
                if (_t.monotonic() - last_pong) > 60.0:
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    break
                continue
            raw = recv_task.result()
            if raw.get("type") == "websocket.disconnect":
                break
            data = raw.get("text") or raw.get("bytes")
            if data == "pong" or (isinstance(data, (bytes, bytearray)) and bytes(data) == b"pong"):
                last_pong = _t.monotonic()
                continue
            try:
                import json
                payload = json.loads(data) if isinstance(data, (str, bytes, bytearray)) else None
            except Exception:
                payload = None
            if not payload or not isinstance(payload, dict):
                continue
            if payload.get("type") == "refreshState":
                try:
                    uid = getattr(ws.state, "user_id", None) or "anon"
                    state_payload = await _build_state_payload(uid)
                    await ws.send_json({"topic": "music.state", "data": state_payload.model_dump()})
                except Exception:
                    pass
            elif payload.get("type") == "pong":
                last_pong = _t.monotonic()
                continue
    finally:
        _ws_clients.discard(ws)
        try:
            dur = int(round(_t.time() - connected_at))
            _logger.info("ws.music.close", extra={"meta": {"duration_s": dur}})
        except Exception:
            pass


__all__ = ["router"]

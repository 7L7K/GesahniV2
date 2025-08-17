from __future__ import annotations

import asyncio
from typing import Dict, Set
import logging
import os
import time

from fastapi import APIRouter, Depends, WebSocket
from pydantic import BaseModel, ConfigDict

from ..deps.user import get_current_user_id
from ..security import verify_ws
from ..deps.clerk_auth import require_user_ws
from ..deps.roles import require_roles


router = APIRouter(tags=["Care"], dependencies=[])
logger = logging.getLogger(__name__)


_topics: Dict[str, Set[WebSocket]] = {}
_lock = asyncio.Lock()
_hs_lock = asyncio.Lock()
_hs_counts: Dict[str, int] = {}
_hs_reset: float = 0.0
_HS_WINDOW_S: float = float(os.getenv("CARE_WS_HANDSHAKE_WINDOW_S", "10") or 10)
_HS_LIMIT: int = int(os.getenv("CARE_WS_HANDSHAKE_LIMIT", "6") or 6)


def _client_ip(ws: WebSocket) -> str:
    try:
        ip = ws.headers.get("X-Forwarded-For")
        if ip:
            return ip.split(",")[0].strip()
        ch = getattr(ws, "client", None)
        return getattr(ch, "host", "anon") or "anon"
    except Exception:
        return "anon"


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


class WSSubscribeExample(BaseModel):
    action: str = "subscribe"
    topic: str = "resident:r1"

    model_config = ConfigDict(json_schema_extra={"example": {"action": "subscribe", "topic": "resident:r1"}})


class WSTopicsInfo(BaseModel):
    subscribe_example: WSSubscribeExample = WSSubscribeExample()
    topics: list[str] = [
        "resident:{resident_id}",
    ]
    events_example: list[str] = [
        "device.heartbeat",
        "alert.created",
        "alert.acknowledged",
        "alert.resolved",
        "tv.config.updated",
    ]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subscribe_example": {"action": "subscribe", "topic": "resident:r1"},
                "topics": ["resident:{resident_id}"],
                "events_example": [
                    "device.heartbeat",
                    "alert.created",
                    "alert.acknowledged",
                    "alert.resolved",
                    "tv.config.updated",
                ],
            }
        }
    )


@router.get("/ws/care", response_model=WSTopicsInfo, responses={200: {"model": WSTopicsInfo}})
async def ws_care_docs(_user_id: str = Depends(get_current_user_id)):
    """WebSocket entry point documentation.

    Connect to ``/v1/ws/care`` and send a JSON message to subscribe to a topic.
    Example payload: ``{"action": "subscribe", "topic": "resident:r1"}``.
    """
    return WSTopicsInfo()


@router.websocket("/ws/care")
async def ws_care(ws: WebSocket, _user_id: str = Depends(get_current_user_id), _roles=Depends(require_roles(["caregiver", "resident"]))):
    # Validate WebSocket Origin explicitly
    origin = ws.headers.get("Origin")
    allowed_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://127.0.0.1:3000")
    origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
    
    if origin and origin not in origins:
        try:
            await ws.close(code=1008, reason="origin_not_allowed")
        except Exception:
            pass
        return
    
    # Prefer Clerk JWT when configured; otherwise fall back to legacy verify_ws
    try:
        if os.getenv("CLERK_ISSUER") or os.getenv("CLERK_JWKS_URL") or os.getenv("CLERK_DOMAIN"):
            await require_user_ws(ws)
        else:
            await verify_ws(ws)
    except Exception:
        # If dependency raised, close handled inside; ensure early return
        return
    try:
        uid = getattr(ws.state, "user_id", None)
    except Exception:
        uid = None
    if not uid:
        # Close with policy violation when unauthenticated only when JWT is enforced
        try:
            jwt_secret = os.getenv("JWT_SECRET")
            require_jwt = os.getenv("REQUIRE_JWT", "1").strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            jwt_secret = None
            require_jwt = False
        if jwt_secret and require_jwt:
            try:
                await ws.close(code=1008, reason="unauthorized")
            except Exception:
                pass
            try:
                logger.info("ws.close policy", extra={"meta": {"endpoint": "/v1/ws/care", "reason": "unauthorized", "code": 1008}})
            except Exception:
                pass
            return
    # Prefer agreed subprotocol; fall back gracefully
    try:
        await ws.accept(subprotocol="json.realtime.v1")
    except Exception:
        await ws.accept()
    # Post-accept handshake burst control (per-IP). Close immediately with 1013 when exceeded.
    try:
        ip = _client_ip(ws)
        test_salt = os.getenv("PYTEST_RUNNING") or os.getenv("PYTEST_CURRENT_TEST") or ""
        key = f"{ip}:{test_salt}" if test_salt else ip
        now = time.monotonic()
        async with _hs_lock:
            global _hs_reset
            if now - float(_hs_reset or 0.0) >= _HS_WINDOW_S:
                _hs_counts.clear()
                _hs_reset = now
            _hs_counts[key] = int(_hs_counts.get(key, 0)) + 1
            count = _hs_counts[key]
        if count > _HS_LIMIT:
            try:
                await ws.close(code=1013, reason="too_busy")
            except Exception:
                pass
            try:
                logger.info("ws.close policy", extra={"meta": {"endpoint": "/v1/ws/care", "reason": "too_busy", "code": 1013, "ip": ip}})
            except Exception:
                pass
            return
    except Exception:
        # Do not fail connection on limiter bookkeeping error
        pass
    try:
        logger.info("ws.accept", extra={"meta": {"endpoint": "/v1/ws/care", "user_id": uid, "subprotocol": "json.realtime.v1"}})
    except Exception:
        pass
    import time as _t
    last_pong = _t.monotonic()
    try:
        while True:
            import asyncio as _aio
            done, _ = await _aio.wait({_aio.create_task(ws.receive_text())}, timeout=25.0)
            if not done:
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
            data = next(iter(done)).result()
            if data == "pong":
                last_pong = _t.monotonic()
                continue
            # Schema-validate client messages
            try:
                import json
                msg = json.loads(data)
            except Exception:
                msg = data
            if isinstance(msg, dict) and msg.get("action") == "subscribe":
                topic = str(msg.get("topic") or "").strip()
                # Enforce resident topic ACL: only self topic or admin
                allow = False
                try:
                    payload = getattr(ws.state, "jwt_payload", None)
                    scopes = []
                    if isinstance(payload, dict):
                        raw = payload.get("scope") or payload.get("scopes") or []
                        scopes = [s.strip() for s in (raw.split() if isinstance(raw, str) else raw) if str(s).strip()]
                    if topic == f"resident:{uid}" or ("admin" in scopes or "admin:write" in scopes):
                        allow = True
                except Exception:
                    allow = False
                if topic.startswith("resident:") and len(topic) > len("resident:") and allow:
                    async with _lock:
                        _topics.setdefault(topic, set()).add(ws)
                else:
                    # ignore invalid or unauthorized topics silently
                    pass
            elif msg == "ping" or (isinstance(msg, dict) and msg.get("action") == "ping"):
                await ws.send_text("pong")
            else:
                # ignore unsupported messages
                pass
    except Exception:
        pass
    finally:
        async with _lock:
            for t in list(_topics.keys()):
                _topics[t].discard(ws)


async def broadcast_resident(resident_id: str, event: str, data: dict) -> None:
    topic = f"resident:{resident_id}"
    await _broadcast(topic, {"event": event, **data})



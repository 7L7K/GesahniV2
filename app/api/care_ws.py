from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import APIRouter, Depends, Request, Response, WebSocket
from pydantic import BaseModel, ConfigDict

from ..api._deps import dep_verify_ws
from ..deps.user import get_current_user_id

router = APIRouter(tags=["Care"], dependencies=[])
logger = logging.getLogger(__name__)


_topics: dict[str, set[WebSocket]] = {}
_lock = asyncio.Lock()
_hs_lock = asyncio.Lock()
_hs_counts: dict[str, int] = {}
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
    """Enhanced topic-based WebSocket broadcasting with improved error handling."""
    async with _lock:
        clients = set(_topics.get(topic) or set())
    if not clients:
        return

    import asyncio as _aio
    import logging as _log
    import time as _time

    logger = _log.getLogger(__name__)
    dead = []
    sem = _aio.Semaphore(int(os.getenv("WS_BROADCAST_CONCURRENCY", "64") or 64))
    start_time = _time.monotonic()

    async def _send(ws: WebSocket) -> None:
        try:
            async with sem:
                await ws.send_json({"topic": topic, "data": payload})
        except Exception as e:
            # Avoid async logging issues in tests
            if os.getenv("WS_DISABLE_ASYNC_LOGGING", "0") != "1":
                logger.debug("ws.broadcast.error: failed_to_send_topic topic=%s user_id=%s error=%s",
                            topic, getattr(ws.state, "user_id", "unknown"), str(e))
            dead.append(ws)

    # Use gather with return_exceptions for parallel sending
    results = await _aio.gather(*[_send(ws) for ws in list(clients)], return_exceptions=True)

    if dead:
        async with _lock:
            for ws in dead:
                try:
                    for t in list(_topics.keys()):
                        _topics[t].discard(ws)
                    user_id = getattr(ws.state, "user_id", "unknown")
                    # Avoid async logging issues in tests
                    if os.getenv("WS_DISABLE_ASYNC_LOGGING", "0") != "1":
                        logger.info("ws.broadcast.cleanup: removed_dead_connection_topic topic=%s user_id=%s", topic, user_id)
                    await ws.close(code=1000, reason="connection_unhealthy")
                except Exception as e:
                    # Avoid async logging issues in tests
                    if os.getenv("WS_DISABLE_ASYNC_LOGGING", "0") != "1":
                        logger.debug("ws.broadcast.cleanup.error: failed_to_close user_id=%s error=%s",
                                    getattr(ws.state, "user_id", "unknown"), str(e))

    # Log broadcast metrics (avoid async logging issues in tests)
    duration = _time.monotonic() - start_time
    if os.getenv("WS_DISABLE_ASYNC_LOGGING", "0") != "1":
        logger.debug("ws.broadcast.complete: topic=%s clients=%d dead=%d duration_ms=%.2f",
                    topic, len(clients), len(dead), duration * 1000)


class WSSubscribeExample(BaseModel):
    action: str = "subscribe"
    topic: str = "resident:r1"

    model_config = ConfigDict(
        json_schema_extra={"example": {"action": "subscribe", "topic": "resident:r1"}}
    )


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


# HTTP handler guard (must come before WebSocket endpoint)
@router.get("/ws/care")
@router.post("/ws/care")
@router.put("/ws/care")
@router.patch("/ws/care")
@router.delete("/ws/care")
async def websocket_http_handler(request: Request):
    try:
        from app.auth_monitoring import record_ws_reconnect_attempt

        record_ws_reconnect_attempt(
            endpoint="/v1/ws/care",
            reason="http_request_to_ws_endpoint",
            user_id="unknown",
        )
    except Exception:
        pass
    return Response(
        content="WebSocket endpoint requires WebSocket protocol",
        status_code=400,
        media_type="text/plain",
        headers={
            "X-WebSocket-Error": "protocol_required",
            "X-WebSocket-Reason": "HTTP requests not supported on WebSocket endpoints",
        },
    )


@router.get(
    "/ws/care/docs", response_model=WSTopicsInfo, responses={200: {"model": WSTopicsInfo}}
)
async def ws_care_docs(_user_id: str = Depends(get_current_user_id)):
    """WebSocket entry point documentation.

    Connect to ``/v1/ws/care`` and send a JSON message to subscribe to a topic.
    Example payload: ``{"action": "subscribe", "topic": "resident:r1"}``.
    """
    return WSTopicsInfo()


@router.websocket("/ws/care")
async def ws_care(ws: WebSocket, _v: None = dep_verify_ws()):
    import logging
    logger = logging.getLogger(__name__)

    logger.info("🏥 ws.care.handler.STARTED", extra={"meta": {
        "origin": ws.headers.get("Origin"),
        "user_agent": ws.headers.get("User-Agent"),
        "query_params": dict(ws.query_params),
        "headers": dict(ws.headers)
    }})

    # Get user_id from WebSocket state (set by dep_verify_ws)
    try:
        uid = getattr(ws.state, "user_id", None)
    except Exception:
        uid = None

    if not uid:
        # This shouldn't happen if dep_verify_ws worked, but handle gracefully
        logger.error("ws.care.auth.failed: no user_id after dep_verify_ws")
        try:
            await ws.close(code=1008, reason="unauthorized")
        except Exception:
            pass
        return

    logger.info("ws.care.auth.success: user_id=%s", uid)
    # Prefer agreed subprotocol; fall back gracefully
    try:
        await ws.accept(subprotocol="json.realtime.v1")
    except Exception:
        await ws.accept()

    # Send hello frame after accept
    try:
        await ws.send_json({"type": "hello", "proto": "json.realtime.v1"})
    except Exception:
        pass  # Don't fail connection if hello fails

    logger.info("ws.care.connection_established")
    import time as _t

    last_pong = _t.monotonic()
    try:
        while True:
            import asyncio as _aio

            done, _ = await _aio.wait(
                {_aio.create_task(ws.receive_text())}, timeout=25.0
            )
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
                    # Get scopes from WebSocket state (set by verify_ws)
                    scopes = getattr(ws.state, "scopes", [])
                    if topic == f"resident:{uid}" or (
                        "admin" in scopes or "admin:write" in scopes
                    ):
                        allow = True
                except Exception:
                    allow = False
                if (
                    topic.startswith("resident:")
                    and len(topic) > len("resident:")
                    and allow
                ):
                    async with _lock:
                        _topics.setdefault(topic, set()).add(ws)
                else:
                    # ignore invalid or unauthorized topics silently
                    pass
            elif msg == "ping" or (
                isinstance(msg, dict) and msg.get("action") == "ping"
            ):
                await ws.send_text("pong")
            else:
                # ignore unsupported messages
                pass
    except Exception:
        pass
    finally:
        # Phase 6.2: Audit WebSocket disconnect
        try:
            from app.audit import append_audit

            append_audit(
                action="ws_disconnect",
                user_id_hashed=uid,
                data={"path": "/v1/ws/care", "endpoint": "/v1/ws/care"},
                ip_address=_client_ip(ws),
            )
        except Exception:
            # Never fail cleanup due to audit issues
            pass

        async with _lock:
            for t in list(_topics.keys()):
                _topics[t].discard(ws)


async def broadcast_resident(resident_id: str, event: str, data: dict) -> None:
    topic = f"resident:{resident_id}"
    await _broadcast(topic, {"event": event, **data})




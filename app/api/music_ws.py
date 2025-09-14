from __future__ import annotations

import asyncio
import logging
import os
import time as _t
from dataclasses import fields
from typing import Any

from fastapi import APIRouter, Request, Response, WebSocket

from app.api._deps import dep_verify_ws
from app.music import get_provider
from app.music.delta import DeltaBuilder
from app.music.models import PlayerState
from app.utils.lru_cache import ws_idempotency_cache
from app.ws_manager import WSConnectionManager, get_ws_manager

router = APIRouter(tags=["Music"])  # mounted under /v1


def prune_to_model(d: dict, model_cls) -> dict:
    """Prune dictionary to only include fields that exist in the model class.

    This prevents WebSocket crashes when unexpected fields are present in device data.
    Falls back to allowing all fields if model introspection fails.
    """
    try:
        # Try Pydantic v2 style first
        if hasattr(model_cls, "model_fields"):
            allowed = set(model_cls.model_fields.keys())
        # Try dataclass style
        elif hasattr(model_cls, "__dataclass_fields__"):
            allowed = set(model_cls.__dataclass_fields__.keys())
        # Try dataclass fields() function
        else:
            allowed = {f.name for f in fields(model_cls)}
    except Exception:
        # If introspection fails, allow all fields as safety net
        logger.warning("prune_to_model: introspection failed, allowing all fields")
        return d

    return {k: v for k, v in d.items() if k in allowed}


def _client_ip(ws: WebSocket) -> str:
    try:
        ip = ws.headers.get("X-Forwarded-For")
        if ip:
            return ip.split(",")[0].strip()
        ch = getattr(ws, "client", None)
        return getattr(ch, "host", "anon") or "anon"
    except Exception:
        return "anon"


def _ws_origin_allowed(ws: WebSocket) -> bool:
    try:
        origin = ws.headers.get("Origin")
        configured = list(getattr(ws.app.state, "allowed_origins", []))  # type: ignore[attr-defined]
        if not configured:
            _env = (
                os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
                or "http://localhost:3000"
            )
            configured = [o.strip() for o in _env.split(",") if o.strip()]
        return (not origin) or (origin in configured)
    except Exception:
        return True


def _validate_envelope(payload: dict) -> tuple[bool, str]:
    """Validate WebSocket message envelope.

    Returns (is_valid, error_message).
    """
    if not isinstance(payload, dict):
        return False, "payload must be an object"

    # Required fields
    if "type" not in payload:
        return False, "missing required field: type"

    if "proto_ver" not in payload:
        return False, "missing required field: proto_ver"

    if payload.get("proto_ver") != 1:
        return False, "unsupported proto_ver, expected 1"

    # Optional but validated fields
    req_id = payload.get("req_id")
    if req_id is not None and not isinstance(req_id, str):
        return False, "req_id must be a string"

    ts = payload.get("ts")
    if ts is not None and not isinstance(ts, int | float):
        return False, "ts must be a number"

    return True, ""


async def _send_ack(ws: WebSocket, req_id: str | None, user_id: str) -> None:
    """Send acknowledgment response within 500ms."""
    ack_payload = {
        "type": "ack",
        "proto_ver": 1,
        "ts": int(_t.time() * 1000),
    }
    if req_id:
        ack_payload["req_id"] = req_id

    try:
        await asyncio.wait_for(ws.send_json(ack_payload), timeout=0.5)
    except TimeoutError:
        logger.warning("ws.music.ack_timeout", extra={"meta": {"user_id": user_id}})
    except Exception as e:
        logger.debug(
            "ws.music.ack_failed", extra={"meta": {"user_id": user_id, "error": str(e)}}
        )


async def _send_error(
    ws: WebSocket, req_id: str | None, code: str, message: str, user_id: str
) -> None:
    """Send error response within 500ms."""
    error_payload = {
        "type": "error",
        "proto_ver": 1,
        "ts": int(_t.time() * 1000),
        "code": code,
        "message": message,
    }
    if req_id:
        error_payload["req_id"] = req_id

    try:
        await asyncio.wait_for(ws.send_json(error_payload), timeout=0.5)
    except TimeoutError:
        logger.warning("ws.music.error_timeout", extra={"meta": {"user_id": user_id}})
    except Exception as e:
        logger.debug(
            "ws.music.error_send_failed",
            extra={"meta": {"user_id": user_id, "error": str(e)}},
        )


async def _dispatch_command(
    ws: WebSocket,
    payload: dict,
    user_id: str,
    manager: WSConnectionManager | None,
    logger: logging.Logger,
    provider,
    current_state,
    _update_current_state,
) -> None:
    """Dispatch WebSocket command with idempotency and ack/error handling."""
    req_id = payload.get("req_id")
    cache_key = None

    # Check idempotency for requests with req_id
    if req_id:
        cache_key = f"{user_id}:{req_id}"
        cached_result = await ws_idempotency_cache.get(cache_key)
        if cached_result is not None:
            # Return cached response
            try:
                await asyncio.wait_for(ws.send_json(cached_result), timeout=0.5)
                return
            except Exception:
                pass  # Fall through to processing

    # Process command
    cmd_type = payload.get("type")
    response_payload = None

    try:
        if cmd_type == "refreshState":
            # Update state from provider
            await _update_current_state()
            if current_state:
                response_payload = {
                    "type": "state",
                    "proto_ver": 1,
                    "ts": int(_t.time() * 1000),
                    "data": current_state.to_dict(),
                    "state_hash": current_state.state_hash(),
                }
                if req_id:
                    response_payload["req_id"] = req_id

        elif cmd_type == "ping":
            response_payload = {
                "type": "pong",
                "proto_ver": 1,
                "ts": int(_t.time() * 1000),
            }
            if req_id:
                response_payload["req_id"] = req_id

        elif cmd_type == "play":
            entity_id = payload.get("entity_id") or payload.get("id")
            entity_type = payload.get("entity_type") or payload.get("type", "track")
            await provider.play(entity_id or "", entity_type)
            # Update state after command
            await _update_current_state()
            # Ack the command
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "pause":
            await provider.pause()
            await _update_current_state()
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "resume":
            await provider.resume()
            await _update_current_state()
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "next":
            await provider.next()
            await _update_current_state()
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "previous":
            await provider.previous()
            await _update_current_state()
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "seek":
            position_ms = payload.get("position_ms", 0)
            await provider.seek(position_ms)
            await _update_current_state()
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "setVolume":
            level = payload.get("level", 50)
            await provider.set_volume(level)
            await _update_current_state()
            await _send_ack(ws, req_id, user_id)

        elif cmd_type == "transferPlayback":
            device_id = payload.get("device_id")
            if device_id:
                await provider.transfer_playback(device_id)
                await _send_ack(ws, req_id, user_id)
            else:
                await _send_error(
                    ws,
                    req_id,
                    "missing_device_id",
                    "device_id required for transferPlayback",
                    user_id,
                )

        elif cmd_type == "queueAdd":
            entity_id = payload.get("entity_id") or payload.get("id")
            entity_type = payload.get("entity_type") or payload.get("type", "track")
            await provider.add_to_queue(entity_id or "", entity_type)
            await _send_ack(ws, req_id, user_id)

        else:
            # Unknown command
            await _send_error(
                ws,
                req_id,
                "unknown_command",
                f"unknown command type: {cmd_type}",
                user_id,
            )
            return

        # Send response
        if response_payload:
            try:
                await asyncio.wait_for(ws.send_json(response_payload), timeout=0.5)
                # Cache successful response
                if cache_key:
                    await ws_idempotency_cache.put(cache_key, response_payload)
            except TimeoutError:
                logger.warning(
                    "ws.music.response_timeout", extra={"meta": {"user_id": user_id}}
                )
            except Exception as e:
                logger.debug(
                    "ws.music.response_failed",
                    extra={"meta": {"user_id": user_id, "error": str(e)}},
                )

        # Send ack for commands that don't have explicit responses
        # Note: ping already sends pong response, so no ack needed

    except Exception as e:
        logger.error(
            "ws.music.command_error",
            extra={"meta": {"user_id": user_id, "command": cmd_type, "error": str(e)}},
        )
        await _send_error(ws, req_id, "command_failed", str(e), user_id)


async def _broadcast(topic: str, payload: dict) -> None:
    """Enhanced WebSocket broadcasting using the connection manager."""
    import logging as _log

    logger = _log.getLogger(__name__)

    # Get connection manager and broadcast to all music connections
    ws_manager = await get_ws_manager()
    music_connections = ws_manager.get_connections_by_metadata("endpoint", "music")

    if not music_connections:
        return

    # Use the connection manager's broadcast method
    message = {"topic": topic, "data": payload}
    await ws_manager.broadcast_to_all(message)

    logger.debug(
        "ws.music.broadcast: topic=%s connections=%d", topic, len(music_connections)
    )


@router.websocket("/ws/music")
async def ws_music(ws: WebSocket, _v: None = dep_verify_ws()):
    import logging

    logger = logging.getLogger(__name__)

    logger.info(
        "🎵 ws.music.handler.STARTED",
        extra={
            "meta": {
                "origin": ws.headers.get("Origin"),
                "user_agent": ws.headers.get("User-Agent"),
                "query_params": dict(ws.query_params),
                "headers": dict(ws.headers),
            }
        },
    )

    # Get user_id from WebSocket state (set by dep_verify_ws)
    try:
        uid = getattr(ws.state, "user_id", None)
    except Exception:
        uid = None

    if not uid:
        # This shouldn't happen if dep_verify_ws worked, but handle gracefully
        logger.error("ws.music.auth.failed: no user_id after dep_verify_ws")
        try:
            await ws.close(code=1008, reason="unauthorized")
        except Exception:
            pass
        return

    logger.info("ws.music.auth.success: user_id=%s", uid)

    # Always accept with subprotocol - never fall back
    try:
        await ws.accept(subprotocol="json.realtime.v1")
        logger.info(
            "ws.music.accept.success",
            extra={"meta": {"subprotocol": "json.realtime.v1"}},
        )
    except Exception as e:
        logger.error("ws.music.accept.failed", extra={"meta": {"error": str(e)}})
        return

    # Initialize manager and provider in background - don't block connection
    manager: WSConnectionManager | None = None
    provider = get_provider()
    current_state: PlayerState | None = None
    delta_builder: DeltaBuilder | None = None
    degraded_mode = True

    async def _init_manager():
        nonlocal manager, degraded_mode
        try:
            manager = await get_ws_manager()
            degraded_mode = False
            logger.info("ws.music.manager.ready", extra={"meta": {"user_id": uid}})
        except Exception as e:
            logger.error(
                "ws.music.manager.init_failed",
                extra={"meta": {"user_id": uid, "error": str(e)}},
            )
            degraded_mode = True

    # Store current state for delta builder (updated by commands)
    current_state: PlayerState | None = None

    async def _update_current_state():
        """Update current state from provider."""
        nonlocal current_state
        try:
            playback_state = await provider.get_state()
            current_state = PlayerState(
                is_playing=getattr(playback_state, "is_playing", False),
                progress_ms=getattr(playback_state, "progress_ms", 0),
                track=getattr(playback_state, "track", None),
                device=getattr(playback_state, "device", None),
                shuffle=getattr(playback_state, "shuffle", False),
                repeat=getattr(playback_state, "repeat", "off"),
                volume_percent=(
                    getattr(playback_state.device, "volume", 50)
                    if getattr(playback_state, "device", None)
                    else 50
                ),
                provider=provider.name,
            )
        except Exception as e:
            logger.error(
                "ws.music.state.get_failed",
                extra={"meta": {"user_id": uid, "error": str(e)}},
            )
            current_state = None

    def _get_current_state() -> PlayerState | None:
        """Get current player state (synchronous for delta builder)."""
        return current_state

    async def _send_delta(payload: dict[str, Any]) -> None:
        """Send delta payload to WebSocket."""
        try:
            await asyncio.wait_for(ws.send_json(payload), timeout=1.0)
        except Exception as e:
            logger.debug(
                "ws.music.delta.send_failed",
                extra={"meta": {"user_id": uid, "error": str(e)}},
            )

    # Start manager initialization in background
    manager_task = asyncio.create_task(_init_manager())

    # Initialize current state
    await _update_current_state()

    # Send hello immediately with mode and timestamp
    hello_payload = {
        "type": "hello",
        "proto": "json.realtime.v1",
        "mode": "degraded" if degraded_mode else "ok",
        "ts": int(_t.time() * 1000),
    }

    try:
        await ws.send_json(hello_payload)
        logger.info(
            "ws.music.hello.sent",
            extra={"meta": {"user_id": uid, "mode": hello_payload["mode"]}},
        )
    except Exception as e:
        logger.error(
            "ws.music.hello.failed", extra={"meta": {"user_id": uid, "error": str(e)}}
        )
        return

    # Send initial state after hello
    if current_state:
        try:
            state_payload = {
                "type": "state_full",
                "proto_ver": 1,
                "ts": int(_t.time() * 1000),
                "state": current_state.to_dict(),
                "state_hash": current_state.state_hash(),
            }
            await ws.send_json(state_payload)
            logger.info("ws.music.initial_state.sent", extra={"meta": {"user_id": uid}})
        except Exception as e:
            logger.error(
                "ws.music.initial_state.failed",
                extra={"meta": {"user_id": uid, "error": str(e)}},
            )

    # Initialize delta builder (without sending initial state again)
    try:
        delta_builder = DeltaBuilder(_get_current_state)
        await delta_builder.start_emitter(_send_delta, send_initial_state=False)
        logger.info("ws.music.delta_builder.ready", extra={"meta": {"user_id": uid}})
    except Exception as e:
        logger.warning(
            "ws.music.delta_builder.init_failed",
            extra={"meta": {"user_id": uid, "error": str(e)}},
        )

    # Phase 6.2: Audit WebSocket connect
    try:
        from app.audit import append_audit

        append_audit(
            action="ws_connect",
            user_id_hashed=uid,
            data={"path": "/v1/ws/music", "endpoint": "/v1/ws/music"},
            ip_address=_client_ip(ws),
        )
    except Exception:
        # Never fail WebSocket connection due to audit issues
        pass

    try:
        logger.info(
            "ws.accept",
            extra={
                "meta": {
                    "endpoint": "/v1/ws/music",
                    "user_id": uid,
                    "subprotocol": "json.realtime.v1",
                }
            },
        )
    except Exception:
        pass

    # Add connection to manager (only if manager is ready)
    conn_state = None
    if manager is not None:
        try:
            conn_state = await manager.add_connection(ws, uid, endpoint="music")
            logger.info(
                "ws.music.connection_established", extra={"meta": {"user_id": uid}}
            )
        except Exception as e:
            logger.warning(
                "ws.music.add_connection.failed",
                extra={"meta": {"user_id": uid, "error": str(e)}},
            )

    _logger = logging.getLogger(__name__)
    connected_at = _t.time()
    last_pong = _t.monotonic()

    logger.info("ws.music.message_loop.start", extra={"meta": {"user_id": uid}})
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
                # Send ping and update connection activity
                try:
                    await ws.send_text("ping")
                    if conn_state:
                        conn_state.update_activity()
                except Exception:
                    break
                # Check for pong timeout
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

            # Handle legacy ping/pong (backward compatibility)
            if data == "pong" or (
                isinstance(data, bytes | bytearray) and bytes(data) == b"pong"
            ):
                last_pong = _t.monotonic()
                if conn_state:
                    conn_state.update_activity()
                continue
            elif data == "ping" or (
                isinstance(data, bytes | bytearray) and bytes(data) == b"ping"
            ):
                await ws.send_text("pong")
                logger.debug("ws.music.ping_handled")
                continue

            # Parse JSON payload
            try:
                import json

                payload = (
                    json.loads(data)
                    if isinstance(data, str | bytes | bytearray)
                    else None
                )
            except Exception:
                payload = None

            if not payload or not isinstance(payload, dict):
                continue

            # Validate envelope
            is_valid, error_msg = _validate_envelope(payload)
            if not is_valid:
                await _send_error(
                    ws, payload.get("req_id"), "invalid_envelope", error_msg, uid
                )
                continue

            # Update activity for valid messages
            if conn_state:
                conn_state.update_activity()

            # Dispatch command with idempotency
            await _dispatch_command(
                ws,
                payload,
                uid,
                manager,
                logger,
                provider,
                current_state,
                _update_current_state,
            )

    finally:
        # Clean up delta builder
        if delta_builder:
            try:
                await delta_builder.stop_emitter()
                logger.debug(
                    "ws.music.delta_builder.stopped", extra={"meta": {"user_id": uid}}
                )
            except Exception as e:
                logger.debug(
                    "ws.music.delta_builder.cleanup_failed",
                    extra={"meta": {"user_id": uid, "error": str(e)}},
                )

        # Clean up manager task
        if not manager_task.done():
            manager_task.cancel()
            try:
                await manager_task
            except _aio.CancelledError:
                pass

        # Remove from connection manager
        if manager is not None and conn_state is not None:
            logger.debug("ws.music.cleanup.start", extra={"meta": {"user_id": uid}})
            await manager.remove_connection(uid)

        try:
            dur = int(round(_t.time() - connected_at))
            logger.info(
                "ws.music.connection_closed",
                extra={"meta": {"user_id": uid, "duration_s": dur}},
            )
        except Exception as e:
            logger.debug(
                "ws.music.cleanup.error",
                extra={"meta": {"user_id": uid, "error": str(e)}},
            )
            pass


# Guard: HTTP -> WS error
@router.get("/ws/music")
@router.post("/ws/music")
@router.put("/ws/music")
@router.patch("/ws/music")
@router.delete("/ws/music")
async def websocket_http_handler(request: Request):
    try:
        from app.auth_monitoring import record_ws_reconnect_attempt

        record_ws_reconnect_attempt(
            endpoint="/v1/ws/music",
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


__all__ = ["router"]

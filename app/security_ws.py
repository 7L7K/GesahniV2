# app/security_ws.py
import logging
import os
import uuid
from urllib.parse import parse_qs

from fastapi import HTTPException
from starlette.websockets import WebSocket

from .security import _jwt_decode, _payload_scopes

log = logging.getLogger(__name__)


async def verify_ws(ws: WebSocket):
    # Origin check (browser WS only) - use single source of truth from app.state
    origin = ws.headers.get("origin")
    allowed_origins = getattr(ws.app.state, "allowed_origins", None)
    if allowed_origins and origin and origin not in allowed_origins:
        await ws.close(code=4403, reason="origin_not_allowed")
        raise HTTPException(status_code=403, detail="origin_not_allowed")

    # If no JWT secret is configured, allow connections (useful for tests/dev)
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        return

    token = None
    # Protocol token (Sec-WebSocket-Protocol: bearer,<token>)
    subproto = ws.headers.get("sec-websocket-protocol")
    if subproto and subproto.lower().startswith("bearer,"):
        token = subproto.split(",", 1)[1].strip()

    # Authorization header
    if not token:
        auth = ws.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(None, 1)[1].strip()

    # Query param fallback
    if not token:
        qs = parse_qs(ws.url.query or "")
        token = (qs.get("token") or [None])[0]

    # Unified extraction for cookies/session
    session_outage = False
    if not token:
        try:
            from .auth_core import (
                extract_token as _extract,
                resolve_session_identity as _resolve_sess,
            )

            src, tok = _extract(ws)
            if src == "access_cookie" and tok:
                token = tok
            elif src == "session" and tok:
                try:
                    ident = _resolve_sess(tok)
                except Exception:
                    ident = None
                    session_outage = True
                if ident and isinstance(ident, dict):
                    ws.state.user_id = ident.get("user_id") or ident.get("sub")
                    scopes = _payload_scopes(ident)
                    ws.state.scopes = scopes
                    return ws.state.user_id
        except Exception:
            pass

    if not token:
        # If we attempted session identity and store was unavailable, surface a clearer reason
        if session_outage:
            await ws.close(code=1013, reason="identity_unavailable")
            raise HTTPException(status_code=503, detail="session_store_unavailable")
        await ws.close(code=4401, reason="missing_token")
        raise HTTPException(status_code=401, detail="missing_token")

    try:
        payload = _jwt_decode(token, key=os.getenv("JWT_SECRET"))  # 60s leeway inside
        ws.state.user_id = payload.get("sub") or payload.get("uid")
        scopes = _payload_scopes(payload)
        ws.state.scopes = scopes
        return ws.state.user_id
    except Exception:
        await ws.close(code=4401, reason="invalid_token")
        raise


# WebSocket observability helpers
async def log_ws_connect(ws: WebSocket, topic: str = None, req_id: str = None):
    """Log WebSocket connection establishment."""
    user_id = getattr(ws.state, "user_id", "anon")
    ws_id = getattr(ws.state, "ws_id", str(uuid.uuid4())[:8])
    ws.state.ws_id = ws_id

    log.info(
        "ws.connect",
        extra={
            "meta": {
                "req_id": req_id or str(uuid.uuid4())[:8],
                "ws_id": ws_id,
                "user_id": user_id,
                "topic": topic or "unknown",
                "event": "connect",
                "client_host": getattr(ws.client, "host", "unknown"),
                "origin": ws.headers.get("origin", "none"),
            }
        },
    )


async def log_ws_close(
    ws: WebSocket, code: int = None, reason: str = None, req_id: str = None
):
    """Log WebSocket connection closure."""
    user_id = getattr(ws.state, "user_id", "anon")
    ws_id = getattr(ws.state, "ws_id", "unknown")
    code = code or getattr(ws, "_close_code", 1000)
    reason = reason or getattr(ws, "_close_reason", "normal_closure")

    log.info(
        "ws.close",
        extra={
            "meta": {
                "req_id": req_id or str(uuid.uuid4())[:8],
                "ws_id": ws_id,
                "user_id": user_id,
                "event": "close",
                "close_code": code,
                "close_reason": reason,
            }
        },
    )


async def log_ws_error(ws: WebSocket, error: Exception, req_id: str = None):
    """Log WebSocket errors."""
    user_id = getattr(ws.state, "user_id", "anon")
    ws_id = getattr(ws.state, "ws_id", "unknown")

    log.error(
        "ws.error",
        extra={
            "meta": {
                "req_id": req_id or str(uuid.uuid4())[:8],
                "ws_id": ws_id,
                "user_id": user_id,
                "event": "error",
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        },
    )

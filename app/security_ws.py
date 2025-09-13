# app/security_ws.py
import logging
import os
import uuid
from urllib.parse import parse_qs

import jwt
from fastapi import HTTPException
from starlette.websockets import WebSocket

from .security import _payload_scopes, jwt_decode
from .ws_metrics import record_ws_auth_attempt, record_ws_auth_failure, record_ws_auth_success

log = logging.getLogger(__name__)


async def verify_ws(ws: WebSocket):
    """Enhanced WebSocket authentication with comprehensive logging and error handling."""

    # Record auth attempt
    record_ws_auth_attempt()

    # Log connection attempt
    try:
        await log_ws_connect(ws, topic="auth_verification")
    except Exception:
        pass  # Don't fail auth due to logging issues

    # Origin check (browser WS only) - use single source of truth from app.state
    origin = ws.headers.get("origin")
    allowed_origins = getattr(ws.app.state, "allowed_origins", None)
    if allowed_origins and origin and origin not in allowed_origins:
        log.warning("ws.auth.deny: origin_not_allowed origin=%s client=%s",
                   origin, getattr(ws.client, "host", "unknown"))
        record_ws_auth_failure("origin_not_allowed")
        try:
            await log_ws_close(ws, code=4403, reason="origin_not_allowed")
        except Exception:
            pass
        await ws.close(code=4403, reason="origin_not_allowed")
        raise HTTPException(status_code=403, detail="origin_not_allowed")

    # If no JWT secret is configured, allow connections (useful for tests/dev)
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        log.info("ws.auth.allow: no_jwt_secret_configured")
        return

    # Allow connections in test mode for easier testing
    pytest_running = os.getenv("PYTEST_RUNNING")
    log.info("ws.auth.bypass_check: PYTEST_RUNNING=%s (type: %s)", pytest_running, type(pytest_running))
    if pytest_running and pytest_running.lower() in ("1", "true", "yes"):
        log.info("ws.auth.allow: test_mode_bypass activated")
        # Set dummy user_id for test mode
        ws.state.user_id = "test_user"
        return True
    else:
        log.info("ws.auth.bypass_check: bypass NOT activated, proceeding with auth")

    token = None
    token_source = "none"

    # Protocol token (Sec-WebSocket-Protocol: bearer,<token>)
    subproto = ws.headers.get("sec-websocket-protocol")
    if subproto and subproto.lower().startswith("bearer,"):
        token = subproto.split(",", 1)[1].strip()
        token_source = "sec-websocket-protocol"

    # Authorization header
    if not token:
        auth = ws.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(None, 1)[1].strip()
            token_source = "authorization_header"

    # Query param fallback
    if not token:
        qs = parse_qs(ws.url.query or "")
        token = (qs.get("token") or qs.get("access_token") or [None])[0]
        if token:
            token_source = "query_param"

    # Unified extraction for cookies/session
    session_outage = False
    if not token:
        try:
            from .auth_core import (
                extract_token as _extract,
            )
            from .auth_core import (
                resolve_session_identity as _resolve_sess,
            )

            src, tok = _extract(ws)
            if src == "access_cookie" and tok:
                token = tok
                token_source = "access_token_cookie"
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
                    log.info("ws.auth.success: session_identity user_id=%s source=%s",
                            ws.state.user_id, src)
                    return ws.state.user_id
        except Exception as e:
            log.warning("ws.auth.error: session_extraction_failed error=%s", str(e))

    if not token:
        # If we attempted session identity and store was unavailable, surface a clearer reason
        if session_outage:
            log.warning("ws.auth.deny: session_store_unavailable")
            try:
                await log_ws_close(ws, code=1013, reason="identity_unavailable")
            except Exception:
                pass
            await ws.close(code=1013, reason="identity_unavailable")
            raise HTTPException(status_code=503, detail="session_store_unavailable")

        log.warning("ws.auth.deny: missing_token client=%s", getattr(ws.client, "host", "unknown"))
        record_ws_auth_failure("missing_token")
        try:
            await log_ws_close(ws, code=4401, reason="missing_token")
        except Exception:
            pass
        await ws.close(code=4401, reason="missing_token")
        from .http_errors import unauthorized
        raise unauthorized(message="authentication required", hint="include token in Authorization header, query param, or cookie")

    try:
        log.info("ws.auth.attempting_jwt_decode: token=%s", token[:20] + "...")
        payload = jwt_decode(token, key=os.getenv("JWT_SECRET"))  # 60s leeway inside
        log.info("ws.auth.jwt_decoded: payload=%s", payload)
        ws.state.user_id = payload.get("sub") or payload.get("uid") or payload.get("user_id")
        scopes = _payload_scopes(payload)
        ws.state.scopes = scopes

        log.info("ws.auth.success: jwt_validated user_id=%s token_source=%s scopes=%s",
                ws.state.user_id, token_source, scopes)

        # Record successful authentication
        record_ws_auth_success()
        try:
            from .auth_monitoring import record_auth_success
            record_auth_success("websocket", ws.state.user_id, getattr(ws.client, "host", "unknown"))
        except Exception:
            pass  # Don't fail auth due to monitoring

        return ws.state.user_id
    except jwt.ExpiredSignatureError:
        log.warning("ws.auth.deny: token_expired user_id=%s", payload.get("sub", "unknown") if 'payload' in locals() else "unknown")
        record_ws_auth_failure("token_expired")
        try:
            await log_ws_close(ws, code=4401, reason="token_expired")
        except Exception:
            pass
        await ws.close(code=4401, reason="token_expired")
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError as e:
        log.warning("ws.auth.deny: invalid_token error=%s", str(e))
        record_ws_auth_failure("invalid_token")
        try:
            await log_ws_close(ws, code=4401, reason="invalid_token")
        except Exception:
            pass
        await ws.close(code=4401, reason="invalid_token")
        raise HTTPException(status_code=401, detail="invalid_token")
    except Exception as e:
        log.error("ws.auth.error: unexpected_error error=%s", str(e))
        record_ws_auth_failure("unexpected_error")
        try:
            await log_ws_close(ws, code=4401, reason="auth_error")
        except Exception:
            pass
        await ws.close(code=4401, reason="auth_error")
        raise HTTPException(status_code=401, detail="authentication_error")


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

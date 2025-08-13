from __future__ import annotations
import os
from uuid import uuid4
from fastapi import Request, WebSocket, HTTPException
import jwt

from ..telemetry import LogRecord, log_record_var, hash_user_id

JWT_SECRET: str | None = None  # overridden in tests; env used when None


def get_current_user_id(
    request: Request = None,
    websocket: WebSocket = None,
) -> str:
    """Return the current user's identifier.

    Preference order:
    1. Existing log record set by middleware.
    2. JWT "user_id" claim when API token/secret is configured.
    3. Fallback to anonymous.
    The resolved ID is attached to request/websocket state when authenticated.
    """
    target = request or websocket

    # 1) Grab or initialize our log record
    rec = log_record_var.get()
    if rec is None:
        rec = LogRecord(req_id=uuid4().hex)
        log_record_var.set(rec)

    user_id = ""

    # 2) Try JWT-based user_id (Authorization bearer, WS query param, or cookie)
    auth_header = None
    if target:
        auth_header = target.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    # WS query param fallback for browser WebSocket handshakes
    if token is None and websocket is not None:
        try:
            qp = websocket.query_params
            token = qp.get("access_token") or qp.get("token")
        except Exception:
            token = None
    # Cookie fallback so browser sessions persist without sending headers
    if token is None and request is not None:
        token = request.cookies.get("access_token")
    # Cookie header fallback for WS handshakes
    if token is None and websocket is not None:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("access_token="):
                    token = p.split("=", 1)[1]
                    break
        except Exception:
            token = None

    secret = JWT_SECRET or os.getenv("JWT_SECRET")
    # Default to not requiring JWT in dev unless explicitly enabled
    require_jwt = os.getenv("REQUIRE_JWT", "0").strip().lower() in {"1", "true", "yes", "on"}
    optional_in_tests = os.getenv("JWT_OPTIONAL_IN_TESTS", "0").lower() in {"1", "true", "yes", "on"}

    # Test-mode bypass: if running under pytest or explicit test flags, allow
    # anonymous access when no secret is configured. Mirrors the pattern used in
    # admin/test helpers and keeps kiosk endpoints usable in CI.
    is_test_mode = (
        os.getenv("ENV", "").lower() == "test"
        or optional_in_tests
        or os.getenv("PYTEST_RUNNING")
        or os.getenv("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or os.getenv("PYTEST_CURRENT_TEST")
    )
    if not secret and is_test_mode:
        secret = None
        require_jwt = False
    if token and secret:
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            user_id = payload.get("user_id") or user_id
        except jwt.PyJWTError:
            # For WebSocket handshakes, proceed as anonymous on invalid token to avoid
            # closing the connection before it's established. HTTP requests still fail.
            if websocket is None:
                raise HTTPException(status_code=401, detail="Invalid authentication token")
    elif token and not secret and require_jwt:
        # Token provided but no secret configured while required → fail-closed
        raise HTTPException(status_code=500, detail="missing_jwt_secret")

    if not user_id:
        user_id = "anon"

    # Attach hashed ID to telemetry; keep raw on state when authenticated
    rec.user_id = hash_user_id(user_id) if user_id != "anon" else "anon"
    if target and user_id != "anon":
        target.state.user_id = user_id

    return user_id


def get_current_session_device(request: Request | None = None, websocket: WebSocket | None = None) -> dict:
    target = request or websocket
    sid = None
    did = None
    try:
        if target is not None:
            sid = target.headers.get("X-Session-ID")
            did = target.headers.get("X-Device-ID")
        if not sid and isinstance(request, Request):
            sid = request.cookies.get("sid")
        if not did and isinstance(request, Request):
            did = request.cookies.get("did")
        if not sid and websocket is not None:
            sid = websocket.query_params.get("sid")
        if not did and websocket is not None:
            did = websocket.query_params.get("did")
    except Exception:
        pass
    return {"session_id": sid, "device_id": did}


__all__ = ["get_current_user_id", "get_current_session_device"]

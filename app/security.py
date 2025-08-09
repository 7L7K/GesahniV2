"""Authentication and rate limiting helpers.

This module is intentionally lightweight so that tests can monkey‑patch the
behaviour without pulling in the full production dependencies.  A backwards
compatible ``_apply_rate_limit`` helper is provided because older tests interact
with it directly.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, List

import jwt
from fastapi import HTTPException, Request, WebSocket, WebSocketException

JWT_SECRET: str | None = None  # backwards compat; actual value read from env
API_TOKEN = os.getenv("API_TOKEN")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
_window = 60.0
_lock = asyncio.Lock()

# Per-user counters used by the HTTP and WS middleware -----------------------
http_requests: Dict[str, int] = {}
ws_requests: Dict[str, int] = {}
# Backwards-compatible aliases expected by some tests
_http_requests = http_requests
_ws_requests = ws_requests

# Legacy per-IP store for the deprecated helper below -----------------------
_requests: Dict[str, List[float]] = {}


def _bucket_rate_limit(
    key: str, bucket: Dict[str, int], limit: int, period: float
) -> bool:
    """Increment ``key`` in ``bucket`` and enforce ``limit`` within ``period``."""

    now = time.time()
    reset = bucket.setdefault("_reset", now)
    if now - reset >= period:
        bucket.clear()
        bucket["_reset"] = now
    count = bucket.get(key, 0) + 1
    bucket[key] = count
    return count <= limit


async def _apply_rate_limit(key: str, record: bool = True) -> bool:
    """Compatibility shim used directly by some legacy tests.

    The function tracks timestamps for ``key`` in the module level ``_requests``
    mapping, pruning entries older than ``_window`` seconds.  When ``record`` is
    false only pruning occurs which allows tests to verify that the dictionary
    is cleaned up.
    """

    now = time.time()
    cutoff = now - _window
    timestamps = [ts for ts in _requests.get(key, []) if ts > cutoff]
    if record:
        timestamps.append(now)
    if timestamps:
        _requests[key] = timestamps
    else:
        _requests.pop(key, None)
    return len(timestamps) <= RATE_LIMIT


async def verify_token(request: Request) -> None:
    """Validate Authorization header as a JWT if a secret is configured."""

    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        return
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        request.state.jwt_payload = payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def rate_limit(request: Request) -> None:
    """Rate limit requests per authenticated user (or IP when unauthenticated)."""

    # Prefer explicit user_id set by deps; otherwise pull from JWT payload
    key = getattr(request.state, "user_id", None)
    if not key:
        payload = getattr(request.state, "jwt_payload", None)
        if isinstance(payload, dict):
            key = payload.get("user_id") or payload.get("sub")
    if not key:
        ip = request.headers.get("X-Forwarded-For")
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = request.client.host if request.client else "anon"
    async with _lock:
        ok = _bucket_rate_limit(key, _http_requests, RATE_LIMIT, _window)
    if not ok:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


async def verify_ws(ws: WebSocket) -> None:
    """JWT validation for WebSocket connections.

    Accepts either an ``Authorization: Bearer <token>`` header or a
    ``?token=...``/``?access_token=...`` query parameter for browser clients
    that cannot set custom headers during the WebSocket handshake.
    When validated, the decoded payload is attached to ``ws.state.jwt_payload``
    and ``ws.state.user_id`` is set if present in the token.
    """

    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        return

    # 1) Prefer Authorization header if present
    auth = ws.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]

    # 2) Fallback to query string for browsers
    if not token:
        qp = ws.query_params
        token = qp.get("token") or qp.get("access_token")

    if not token:
        raise WebSocketException(code=1008)

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        ws.state.jwt_payload = payload
        uid = payload.get("user_id") or payload.get("sub")
        if uid:
            ws.state.user_id = uid
    except jwt.PyJWTError:
        raise WebSocketException(code=1008)


async def rate_limit_ws(ws: WebSocket) -> None:
    """Per-user rate limiting for WebSocket connections."""

    key = getattr(ws.state, "user_id", None)
    if not key:
        payload = getattr(ws.state, "jwt_payload", None)
        if isinstance(payload, dict):
            key = payload.get("user_id") or payload.get("sub")
    if not key:
        ip = ws.headers.get("X-Forwarded-For")
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = ws.client.host if ws.client else "anon"
    async with _lock:
        ok = _bucket_rate_limit(key, _ws_requests, RATE_LIMIT, _window)
    if not ok:
        raise WebSocketException(code=1013)


__all__ = [
    "verify_token",
    "rate_limit",
    "verify_ws",
    "rate_limit_ws",
    "_apply_rate_limit",
    "_http_requests",
    "_ws_requests",
    "_requests",
]

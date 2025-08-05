import os
import time
import asyncio
from typing import Dict, List

import jwt
from fastapi import Request, HTTPException, WebSocket

JWT_SECRET = os.getenv("JWT_SECRET")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
_window = 60.0
_lock = asyncio.Lock()
_requests: Dict[str, List[float]] = {}


async def verify_token(request: Request) -> None:
    """Validate Authorization header as a JWT if a secret is configured.

    On success the decoded payload is attached to ``request.state.jwt_payload``.
    """
    if not JWT_SECRET:
        return
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        request.state.jwt_payload = payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def rate_limit(request: Request) -> None:
    """Rate limit requests per authenticated user (or IP when unauthenticated)."""
    key = getattr(request.state, "user_id", None)
    if not key:
        key = request.headers.get("X-Forwarded-For") or (
            request.client.host if request.client else "anon"
        )
    await _apply_rate_limit(key)


async def verify_ws(ws: WebSocket) -> None:
    """JWT validation for WebSocket connections."""
    if not JWT_SECRET:
        return
    auth = ws.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        await ws.close(code=1008)
        raise HTTPException(status_code=1008, detail="Unauthorized")
    token = auth.split(" ", 1)[1]
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        await ws.close(code=1008)
        raise HTTPException(status_code=1008, detail="Unauthorized")


async def rate_limit_ws(ws: WebSocket) -> None:
    """Per-user rate limiting for WebSocket connections."""
    key = getattr(ws.state, "user_id", None)
    if not key:
        key = ws.headers.get("X-Forwarded-For") or (
            ws.client.host if ws.client else "anon"
        )
    await _apply_rate_limit(key, ws)


async def _apply_rate_limit(
    key: str, ws: WebSocket | None = None, record: bool = True
) -> None:
    now = time.time()
    async with _lock:
        timestamps = _requests.get(key, [])
        fresh = [ts for ts in timestamps if now - ts < _window]
        if record and len(fresh) >= RATE_LIMIT:
            if ws is not None:
                await ws.close(code=1013)
                raise HTTPException(status_code=1013, detail="Rate limit exceeded")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        if record:
            fresh.append(now)
        if fresh:
            _requests[key] = fresh
        elif key in _requests:
            del _requests[key]

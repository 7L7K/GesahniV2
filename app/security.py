import os
import time
import asyncio
from typing import Dict

import jwt
from fastapi import Request, HTTPException, WebSocket, WebSocketException

JWT_SECRET = os.getenv("JWT_SECRET")
API_TOKEN = os.getenv("API_TOKEN")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
_window = 60.0
_lock = asyncio.Lock()
_http_requests: Dict[str, int] = {}
_ws_requests: Dict[str, int] = {}

def _apply_rate_limit(
    key: str, bucket: Dict[str, int], limit: int, period: float
) -> bool:
    now = time.time()
    reset = bucket.get("_reset", now)
    if now - reset >= period:
        bucket.clear()
        bucket["_reset"] = now
    count = bucket.get(key, 0) + 1
    bucket[key] = count
    return count <= limit

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
        ip = request.headers.get("X-Forwarded-For")
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = request.client.host if request.client else "anon"
    async with _lock:
        ok = _apply_rate_limit(key, _http_requests, RATE_LIMIT, _window)
    if not ok:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

async def verify_ws(ws: WebSocket) -> None:
    """JWT validation for WebSocket connections."""
    if not JWT_SECRET:
        return
    auth = ws.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise WebSocketException(code=1008)
    token = auth.split(" ", 1)[1]
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise WebSocketException(code=1008)

async def rate_limit_ws(ws: WebSocket) -> None:
    """Per-user rate limiting for WebSocket connections."""
    key = getattr(ws.state, "user_id", None)
    if not key:
        ip = ws.headers.get("X-Forwarded-For")
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = ws.client.host if ws.client else "anon"
    async with _lock:
        ok = _apply_rate_limit(key, _ws_requests, RATE_LIMIT, _window)
    if not ok:
        raise WebSocketException(code=1013)

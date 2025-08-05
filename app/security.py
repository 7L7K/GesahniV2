import os
import time
import asyncio
from typing import Dict, List

import jwt
from fastapi import Request, HTTPException, WebSocket

API_TOKEN = os.getenv("API_TOKEN")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
_window = 60.0
_lock = asyncio.Lock()
_requests: Dict[str, List[float]] = {}


async def verify_token(request: Request) -> None:
    """Validate Authorization header as a JWT if a secret is configured."""
    if not API_TOKEN:
        return
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth.split(" ", 1)[1]
    try:
        jwt.decode(token, API_TOKEN, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def rate_limit(request: Request) -> None:
    """Rate limit requests per authenticated user (or IP when unauthenticated)."""
    key = getattr(request.state, "user_id", None)
    if not key:
        key = request.client.host if request.client else "anon"
    now = time.time()
    async with _lock:
        timestamps = _requests.setdefault(key, [])
        fresh = [ts for ts in timestamps if now - ts < _window]
        if len(fresh) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        fresh.append(now)
        _requests[key] = fresh


async def verify_ws(ws: WebSocket) -> None:
    """JWT validation for WebSocket connections."""
    if not API_TOKEN:
        return
    auth = ws.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        await ws.close(code=1008)
        raise HTTPException(status_code=1008, detail="Unauthorized")
    token = auth.split(" ", 1)[1]
    try:
        jwt.decode(token, API_TOKEN, algorithms=["HS256"])
    except jwt.PyJWTError:
        await ws.close(code=1008)
        raise HTTPException(status_code=1008, detail="Unauthorized")


async def rate_limit_ws(ws: WebSocket) -> None:
    """Per-user rate limiting for WebSocket connections."""
    key = getattr(ws.state, "user_id", None)
    if not key:
        key = ws.client.host if ws.client else "anon"
    now = time.time()
    async with _lock:
        timestamps = _requests.setdefault(key, [])
        fresh = [ts for ts in timestamps if now - ts < _window]
        if len(fresh) >= RATE_LIMIT:
            await ws.close(code=1013)
            raise HTTPException(status_code=1013, detail="Rate limit exceeded")
        fresh.append(now)
        _requests[key] = fresh

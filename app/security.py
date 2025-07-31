import os
import time
import asyncio
from typing import Dict, List
from fastapi import Request, HTTPException, WebSocket

API_TOKEN = os.getenv("API_TOKEN")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
_window = 60.0
_lock = asyncio.Lock()
_requests: Dict[str, List[float]] = {}

async def verify_token(request: Request) -> None:
    if not API_TOKEN:
        return
    auth = request.headers.get("Authorization")
    expected = f"Bearer {API_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

async def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "anon"
    now = time.time()
    async with _lock:
        timestamps = _requests.setdefault(ip, [])
        fresh = [ts for ts in timestamps if now - ts < _window]
        if len(fresh) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        fresh.append(now)
        _requests[ip] = fresh


async def verify_ws(ws: WebSocket) -> None:
    if not API_TOKEN:
        return
    auth = ws.headers.get("Authorization")
    expected = f"Bearer {API_TOKEN}"
    if auth != expected:
        await ws.close(code=1008)
        raise HTTPException(status_code=1008, detail="Unauthorized")


async def rate_limit_ws(ws: WebSocket) -> None:
    ip = ws.client.host if ws.client else "anon"
    now = time.time()
    async with _lock:
        timestamps = _requests.setdefault(ip, [])
        fresh = [ts for ts in timestamps if now - ts < _window]
        if len(fresh) >= RATE_LIMIT:
            await ws.close(code=1013)
            raise HTTPException(status_code=1013, detail="Rate limit exceeded")
        fresh.append(now)
        _requests[ip] = fresh

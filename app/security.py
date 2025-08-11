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
import hmac
import hashlib
from fastapi import Header

import jwt
from fastapi import HTTPException, Request, WebSocket, WebSocketException, Depends

JWT_SECRET: str | None = None  # backwards compat; actual value read from env
API_TOKEN = os.getenv("API_TOKEN")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
_window = 60.0
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "20"))
_burst_window = float(os.getenv("RATE_LIMIT_BURST_WINDOW", "10"))
_lock = asyncio.Lock()

# Per-user counters used by the HTTP and WS middleware -----------------------
http_requests: Dict[str, int] = {}
ws_requests: Dict[str, int] = {}
# Additional short-window buckets for burst allowances
http_burst: Dict[str, int] = {}
ws_burst: Dict[str, int] = {}
# Backwards-compatible aliases expected by some tests
_http_requests = http_requests
_ws_requests = ws_requests
# Back-compat exports for tests if needed
_http_burst = http_burst
_ws_burst = ws_burst

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


def _bucket_retry_after(bucket: Dict[str, int], period: float) -> int:
    """Return seconds until this bucket resets (rounded up)."""

    now = time.time()
    reset = float(bucket.get("_reset", now))
    remaining = (reset + period) - now
    return int(max(0, int(remaining + 0.999)))


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
    require_jwt = os.getenv("REQUIRE_JWT", "1").strip().lower() in {"1", "true", "yes", "on"}
    if not jwt_secret:
        # Fail-closed when required
        if require_jwt:
            raise HTTPException(status_code=500, detail="missing_jwt_secret")
        # Otherwise operate in pass-through mode (dev/test)
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
    """Rate limit requests per authenticated user (or IP when unauthenticated).

    When the limit is exceeded, we attach a short-lived Retry-After hint via the
    raised HTTPException's detail so the caller can read a suggested wait time.
    """

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
        ok_b = _bucket_rate_limit(key, http_burst, RATE_LIMIT_BURST, _burst_window)
        retry_b = _bucket_retry_after(http_burst, _burst_window)
        if not ok_b:
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "retry_after": retry_b},
                headers={"Retry-After": str(retry_b)},
            )
        ok_long = _bucket_rate_limit(key, _http_requests, RATE_LIMIT, _window)
        retry_long = _bucket_retry_after(_http_requests, _window)
    if not ok_long:
        # Include Retry-After header for clients; also JSON detail for compatibility
        retry_after = retry_long
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


async def verify_ws(websocket: WebSocket) -> None:
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
    auth = websocket.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]

    # 2) Fallback to query string for browsers
    if not token:
        qp = websocket.query_params
        token = qp.get("token") or qp.get("access_token")

    if not token:
        # Allow unauthenticated WS when no token is provided; downstream can treat as anon
        return

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        websocket.state.jwt_payload = payload
        uid = payload.get("user_id") or payload.get("sub")
        if uid:
            websocket.state.user_id = uid
    except jwt.PyJWTError:
        # Be lenient for browser clients; proceed as anonymous on decode failure
        return


async def rate_limit_ws(websocket: WebSocket) -> None:
    """Per-user rate limiting for WebSocket connections."""

    key = getattr(websocket.state, "user_id", None)
    if not key:
        payload = getattr(websocket.state, "jwt_payload", None)
        if isinstance(payload, dict):
            key = payload.get("user_id") or payload.get("sub")
    if not key:
        ip = websocket.headers.get("X-Forwarded-For")
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = websocket.client.host if websocket.client else "anon"
    async with _lock:
        ok_long = _bucket_rate_limit(key, _ws_requests, RATE_LIMIT, _window)
        ok_b = _bucket_rate_limit(key, ws_burst, RATE_LIMIT_BURST, _burst_window)
    if not (ok_long and ok_b):
        raise WebSocketException(code=1013)


# ---------------------------------------------------------------------------
# Nonce helpers for state-changing routes
# ---------------------------------------------------------------------------

_nonce_ttl = int(os.getenv("NONCE_TTL_SECONDS", "120"))
_nonce_store: Dict[str, float] = {}


async def require_nonce(request: Request) -> None:
    """Enforce a one-time nonce for state-changing requests.

    Header: X-Nonce: <random-string>
    Enabled when REQUIRE_NONCE env is truthy.
    """

    if os.getenv("REQUIRE_NONCE", "0").lower() not in {"1", "true", "yes"}:
        return
    nonce = request.headers.get("X-Nonce")
    if not nonce:
        raise HTTPException(status_code=400, detail="missing_nonce")
    now = time.time()
    async with _lock:
        # prune expired
        expired = [n for n, ts in list(_nonce_store.items()) if now - ts > _nonce_ttl]
        for n in expired:
            _nonce_store.pop(n, None)
        if nonce in _nonce_store:
            raise HTTPException(status_code=409, detail="nonce_reused")
        _nonce_store[nonce] = now


# ---------------------------------------------------------------------------
# Webhook signing/verification (e.g., HA callbacks)
# ---------------------------------------------------------------------------

def _load_webhook_secrets() -> List[str]:
    # Allow multiple secrets for rotation via env or file
    secrets: List[str] = []
    env_val = os.getenv("HA_WEBHOOK_SECRETS", "")
    if env_val:
        secrets.extend([s.strip() for s in env_val.split(",") if s.strip()])
    try:
        from pathlib import Path

        path = Path(os.getenv("HA_WEBHOOK_SECRET_FILE", "data/ha_webhook_secret.txt"))
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s:
                    secrets.append(s)
    except Exception:
        pass
    # Legacy single env
    single = os.getenv("HA_WEBHOOK_SECRET")
    if single:
        secrets.append(single)
    # dedupe while preserving order
    seen: Dict[str, None] = {}
    out: List[str] = []
    for s in secrets:
        if s not in seen:
            seen[s] = None
            out.append(s)
    return out


def sign_webhook(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def verify_webhook(request: Request, x_signature: str | None = Header(default=None)) -> bytes:
    """Verify webhook signature and return the raw body.

    Expects hex HMAC-SHA256 in X-Signature header.
    """

    body = await request.body()
    secrets = _load_webhook_secrets()
    if not secrets:
        raise HTTPException(status_code=500, detail="webhook_secret_missing")
    sig = (x_signature or "").strip().lower()
    for s in secrets:
        calc = sign_webhook(body, s)
        if hmac.compare_digest(calc.lower(), sig):
            return body
    raise HTTPException(status_code=401, detail="invalid_signature")


def rotate_webhook_secret() -> str:
    """Generate and persist a new webhook secret in the optional secret file.

    Returns the new secret; callers must distribute it to senders.
    """

    import secrets as _secrets
    from pathlib import Path

    new = _secrets.token_hex(16)
    path = Path(os.getenv("HA_WEBHOOK_SECRET_FILE", "data/ha_webhook_secret.txt"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        contents = "\n".join([new] + [line.strip() for line in existing if line.strip()]) + "\n"
        path.write_text(contents, encoding="utf-8")
    except Exception:
        pass
    return new


__all__ = [
    "verify_token",
    "rate_limit",
    "verify_ws",
    "rate_limit_ws",
    "require_nonce",
    "verify_webhook",
    "rotate_webhook_secret",
    "_apply_rate_limit",
    "_http_requests",
    "_ws_requests",
    "_requests",
]

# ---------------------------------------------------------------------------
# Public helpers for rate limit metadata
# ---------------------------------------------------------------------------

def _current_key(request: Request | None) -> str:
    if request is None:
        return "anon"
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
    return str(key)


def get_rate_limit_snapshot(request: Request | None) -> dict:
    """Return a snapshot of long and burst rate limit state for headers."""
    key = _current_key(request)
    # Long window
    long_count = int(_http_requests.get(key, 0))
    long_limit = RATE_LIMIT
    long_reset = _bucket_retry_after(_http_requests, _window)
    long_remaining = max(0, long_limit - long_count)
    # Burst window
    burst_count = int(http_burst.get(key, 0))
    burst_limit = RATE_LIMIT_BURST
    burst_reset = _bucket_retry_after(http_burst, _burst_window)
    burst_remaining = max(0, burst_limit - burst_count)
    return {
        "limit": long_limit,
        "remaining": long_remaining,
        "reset": long_reset,
        "burst_limit": burst_limit,
        "burst_remaining": burst_remaining,
        "burst_reset": burst_reset,
    }

__all__.append("get_rate_limit_snapshot")

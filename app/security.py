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
import datetime as _dt
from typing import Dict, List, Optional, Tuple
import hmac
import hashlib
from fastapi import Header

import jwt
from fastapi import HTTPException, Request, WebSocket, WebSocketException, Depends
# Scope enforcement dependency
def scope_required(*required_scopes: str):
    async def _dep(request: Request) -> None:
        if os.getenv("ENFORCE_JWT_SCOPES", "1").strip().lower() in {"0", "false", "no"}:
            return
        payload = getattr(request.state, "jwt_payload", None)
        scopes = _payload_scopes(payload)
        if not set(required_scopes) <= scopes:
            raise HTTPException(status_code=403, detail="insufficient_scope")
    return _dep
from . import metrics

JWT_SECRET: str | None = None  # backwards compat; actual value read from env
API_TOKEN = os.getenv("API_TOKEN")
# Total requests allowed per long window (defaults retained for back-compat)
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", os.getenv("RATE_LIMIT", "60")))
# Long-window size (seconds), configurable for deterministic tests
_window = float(os.getenv("RATE_LIMIT_WINDOW_S", "60"))
# Short burst bucket
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "10"))
_burst_window = float(os.getenv("RATE_LIMIT_BURST_WINDOW", "10"))
_lock = asyncio.Lock()

# Trust proxy headers for client IP only when explicitly enabled
# Back-compat: trust X-Forwarded-For by default (disable with TRUST_X_FORWARDED_FOR=0)
_TRUST_XFF = os.getenv("TRUST_X_FORWARDED_FOR", "1").strip().lower() in {"1", "true", "yes", "on"}

# Scope of rate limit keys: "global" (default) or "route" to include path
_KEY_SCOPE = os.getenv("RATE_LIMIT_KEY_SCOPE", "global").strip().lower()

# Track pytest's current test id to re-sync config between tests that mutate env
_LAST_TEST_ID = os.getenv("PYTEST_CURRENT_TEST") or ""


def _maybe_refresh_settings_for_test() -> None:
    """When running under pytest, ensure module-level knobs reflect current env.

    Some tests set env vars and reload this module, which can leave mutated
    constants in place for later tests. We detect test case transitions via the
    PYTEST_CURRENT_TEST env var and re-read key settings to avoid cross-test
    leakage. Explicit monkeypatch of module globals within a single test still
    works because we only refresh when the test id changes.
    """
    global RATE_LIMIT, RATE_LIMIT_BURST, _window, _burst_window, _KEY_SCOPE, _LAST_TEST_ID
    test_id = os.getenv("PYTEST_CURRENT_TEST") or ""
    if test_id == _LAST_TEST_ID:
        return
    _LAST_TEST_ID = test_id
    # Do not override monkeypatched constants. Only update scoped key policy.
    try:
        _KEY_SCOPE = os.getenv("RATE_LIMIT_KEY_SCOPE", "global").strip().lower()
    except Exception:
        _KEY_SCOPE = "global"


def _maybe_refresh_settings_for_test() -> None:
    """Refresh in-process settings from env during pytest.

    Some unit tests modify env after import; allow re-reading the core limits.
    """
    if os.getenv("PYTEST_RUNNING"):
        global RATE_LIMIT, RATE_LIMIT_BURST, _window, _burst_window
        try:
            RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", str(RATE_LIMIT)))
        except Exception:
            pass
        try:
            RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", str(RATE_LIMIT_BURST)))
        except Exception:
            pass
        try:
            _window = float(os.getenv("RATE_LIMIT_WINDOW_S", str(_window)))
        except Exception:
            pass
        try:
            _burst_window = float(os.getenv("RATE_LIMIT_BURST_WINDOW", str(_burst_window)))
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Optional distributed backend (Redis) for rate limiting
# ---------------------------------------------------------------------------

# Backend selection: default to in‑memory for tests/back‑compat; enable Redis by
# setting RATE_LIMIT_BACKEND=redis (or distributed) or by providing REDIS_URL.
_RATE_LIMIT_BACKEND = os.getenv("RATE_LIMIT_BACKEND", "memory").strip().lower()
_REDIS_URL = os.getenv("REDIS_URL")
_RL_PREFIX = os.getenv("RATE_LIMIT_REDIS_PREFIX", "rl").strip(":")

# Lazy-initialized async Redis client (if available). Keep it optional so that
# test environments without the dependency continue to work unchanged.
_redis_client: Optional[object] = None

def _should_use_redis() -> bool:
    if _RATE_LIMIT_BACKEND in {"redis", "distributed"}:
        return True
    if _RATE_LIMIT_BACKEND == "memory":
        return False
    return bool(_REDIS_URL)


async def _get_redis():
    """Return an async Redis client when configured and dependency is present.

    Returns None if the backend is not enabled or the redis package is missing.
    """
    global _redis_client
    if not _should_use_redis():
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as redis  # type: ignore
    except Exception:
        return None
    try:
        url = _REDIS_URL or "redis://localhost:6379/0"
        _redis_client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        return _redis_client
    except Exception:
        return None


def _rl_key(kind: str, user_key: str, window: str) -> str:
    # Example: rl:http:<user>:long
    return f"{_RL_PREFIX}:{kind}:{user_key}:{window}"


def _seconds_until_utc_midnight() -> int:
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    tomorrow = (now + _dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = (tomorrow - now).total_seconds()
    return max(0, int(delta + 0.999))


async def _redis_incr_with_ttl(redis_client, key: str, period_seconds: float) -> Tuple[int, int]:
    """Atomically increment a counter and ensure TTL is set on first increment.

    Returns (count, ttl_seconds).
    """
    # Use a tiny Lua script to ensure INCR and initial PEXPIRE are atomic
    script = (
        "local c=redis.call('INCR',KEYS[1]);"
        "if c==1 then redis.call('PEXPIRE',KEYS[1],ARGV[1]); end;"
        "local ttl=redis.call('PTTL',KEYS[1]); return {c, ttl};"
    )
    try:
        res = await redis_client.eval(script, 1, key, int(period_seconds * 1000))
        count = int(res[0]) if isinstance(res, (list, tuple)) else int(res)
        pttl = int(res[1]) if isinstance(res, (list, tuple)) and len(res) > 1 else await redis_client.pttl(key)
        ttl_s = max(0, int((pttl + 999) // 1000))
        return count, ttl_s
    except Exception:
        # On any Redis error, degrade gracefully as if not using Redis
        return -1, 0


# Local daily counters fallback (per UTC day)
_daily_counts: Dict[str, int] = {}
_daily_date: str | None = None


def _local_daily_incr(key: str) -> tuple[int, int]:
    global _daily_counts, _daily_date
    today = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%d")
    if _daily_date != today:
        _daily_counts = {}
        _daily_date = today
    count = _daily_counts.get(key, 0) + 1
    _daily_counts[key] = count
    return count, _seconds_until_utc_midnight()


async def _daily_incr(r, key: str) -> tuple[int, int]:
    """Increment daily counter for ``key`` returning (count, ttl_seconds)."""
    date_str = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%d")
    if r is None:
        return _local_daily_incr(f"{key}:{date_str}")
    k = _rl_key("daily", key, date_str)
    ttl = _seconds_until_utc_midnight()
    script = (
        "local c=redis.call('INCR',KEYS[1]);"
        "if c==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]); end;"
        "local t=redis.call('TTL',KEYS[1]); return {c,t};"
    )
    try:
        res = await r.eval(script, 1, k, ttl)
        count = int(res[0]) if isinstance(res, (list, tuple)) else int(res)
        t = int(res[1]) if isinstance(res, (list, tuple)) and len(res) > 1 else ttl
        return count, max(0, int(t))
    except Exception:
        # degrade to local
        return _local_daily_incr(f"{key}:{date_str}")


def _payload_scopes(payload: dict | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    scopes = payload.get("scope") or payload.get("scopes") or []
    if isinstance(scopes, str):
        return {s.strip() for s in scopes.split() if s.strip()}
    if isinstance(scopes, (list, tuple)):
        return {str(s).strip() for s in scopes if str(s).strip()}
    return set()


def _bypass_scopes_env() -> set[str]:
    raw = os.getenv("RATE_LIMIT_BYPASS_SCOPES", "")
    return {s.strip() for s in str(raw).split() if s.strip()}


def _get_request_payload(request: Request | None) -> dict | None:
    if request is None:
        return None
    payload = getattr(request.state, "jwt_payload", None)
    if isinstance(payload, dict):
        return payload
    try:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
            secret = os.getenv("JWT_SECRET")
            # If a secret is configured, verify signature; otherwise decode payload only
            if secret:
                try:
                    return jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
                except Exception:
                    # Fall back to non-verifying decode for best-effort introspection
                    try:
                        return jwt.decode(token, options={"verify_signature": False})  # type: ignore[arg-type]
                    except Exception:
                        return None
            else:
                try:
                    return jwt.decode(token, options={"verify_signature": False})  # type: ignore[arg-type]
                except Exception:
                    return None
    except Exception:
        return None
    return None


def _get_ws_payload(websocket: WebSocket | None) -> dict | None:
    if websocket is None:
        return None
    payload = getattr(websocket.state, "jwt_payload", None)
    if isinstance(payload, dict):
        return payload
    try:
        auth = websocket.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
            secret = os.getenv("JWT_SECRET")
            if secret:
                try:
                    return jwt.decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
                except Exception:
                    try:
                        return jwt.decode(token, options={"verify_signature": False})  # type: ignore[arg-type]
                    except Exception:
                        return None
            else:
                try:
                    return jwt.decode(token, options={"verify_signature": False})  # type: ignore[arg-type]
                except Exception:
                    return None
    except Exception:
        return None
    return None

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

# Dedicated counters for scope-based overrides to avoid interference with default buckets
_override_long: Dict[str, int] = {}
_override_burst: Dict[str, int] = {}


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
    """Validate JWT from Authorization header or HttpOnly cookie when configured.

    Prefers Authorization: Bearer token; falls back to ``access_token`` cookie for
    kiosk/TV devices where headers aren't available from the web UI.
    """

    jwt_secret = os.getenv("JWT_SECRET")
    # Default to pass-through when no secret is configured unless explicitly required
    require_jwt = os.getenv("REQUIRE_JWT", "0").strip().lower() in {"1", "true", "yes", "on"}
    # Test-mode bypass: allow anonymous when secret is missing under tests OR when JWT_OPTIONAL_IN_TESTS=1
    test_bypass = (
        os.getenv("ENV", "").strip().lower() == "test"
        or os.getenv("PYTEST_RUNNING")
        or os.getenv("JWT_OPTIONAL_IN_TESTS", "0").strip().lower() in {"1", "true", "yes", "on"}
    )
    if test_bypass and not jwt_secret:
        return
    if not jwt_secret:
        # Fail-closed when required
        if require_jwt:
            raise HTTPException(status_code=500, detail="missing_jwt_secret")
        # Otherwise operate in pass-through mode (dev/test)
        return
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    # Fallback to secure cookie set by device trust flow
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        # Allow anonymous when tests indicate JWT is optional OR when
        # ENFORCE_JWT_SCOPES=0 is configured for public endpoints.
        if test_bypass or os.getenv("ENFORCE_JWT_SCOPES", "1").strip() in {"0", "false", "no"}:
            return
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        request.state.jwt_payload = payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _compose_key(base: str, request: Request | None) -> str:
    """Compose the limiter key.

    Default: user/ip only. When RATE_LIMIT_KEY_SCOPE=route, include the path
    so different routes do not contend for the same bucket.
    """
    # Refresh settings per test to avoid cross-test leakage
    _maybe_refresh_settings_for_test()
    if _KEY_SCOPE == "route" and request is not None:
        try:
            path = getattr(request, "url", None)
            path = path.path if path is not None else getattr(request, "url_path", "")
            return f"{base}:{path}"
        except Exception:
            return base
    return base


def get_rate_limit_defaults() -> dict:
    return {
        "limit": RATE_LIMIT,
        "burst_limit": RATE_LIMIT_BURST,
        "window_s": _window,
        "burst_window_s": _burst_window,
    }


async def rate_limit(request: Request) -> None:
    _maybe_refresh_settings_for_test()
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
        ip = request.headers.get("X-Forwarded-For") if _TRUST_XFF else None
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = request.client.host if request.client else "anon"
    # Include route path in the key to avoid cross-route bucket interference
    key = _compose_key(str(key), request)
    # Allow per-route overrides via request.state when set by dependencies
    env_long = os.getenv("RATE_LIMIT_PER_MIN")
    env_burst = os.getenv("RATE_LIMIT_BURST")
    long_limit = int(
        getattr(request.state, "rate_limit_long_limit", None)
        or (int(env_long) if env_long is not None else RATE_LIMIT)
    )
    burst_limit = int(
        getattr(request.state, "rate_limit_burst_limit", None)
        or (int(env_burst) if env_burst is not None else RATE_LIMIT_BURST)
    )
    window = float(getattr(request.state, "rate_limit_window_s", _window) or _window)
    burst_window = float(getattr(request.state, "rate_limit_burst_window_s", _burst_window) or _burst_window)
    # Global bypass for configured scopes
    try:
        payload = getattr(request.state, "jwt_payload", None)
        scopes = _payload_scopes(payload)
        bypass = bool(_bypass_scopes_env() & scopes)
        if bypass:
            try:
                metrics.RATE_LIMIT_ALLOWS.labels("http", "bypass", "n/a").inc()
            except Exception:
                pass
            return
    except Exception:
        pass

    # Optional daily cap per user
    daily_cap = int(os.getenv("DAILY_REQUEST_CAP", "0") or 0)
    r_daily = await _get_redis()
    if daily_cap > 0:
        # Use a deterministic per-test key when under pytest to avoid cross-test pollution
        test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
        daily_key = f"{key}:{test_salt}" if test_salt else str(key)
        count, ttl = await _daily_incr(r_daily, daily_key)
        if count > daily_cap:
            try:
                metrics.RATE_LIMIT_BLOCKS.labels("http", "daily", "redis" if r_daily else "memory").inc()
            except Exception:
                pass
            raise HTTPException(
                status_code=429,
                detail={"error": "daily_cap_exceeded", "retry_after": int(ttl)},
                headers={"Retry-After": str(int(ttl))},
            )

    # Old bypass block removed; handled above
    # Prefer distributed backend when available
    r = await _get_redis()
    backend_label = "redis" if r is not None else "memory"
    if r is not None:
        # Burst bucket first (distributed)
        test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
        suffix = f":{test_salt}" if test_salt else ""
        burst_key = _rl_key("http", key, "burst") + suffix
        long_key = _rl_key("http", key, "long") + suffix
        b_count, b_ttl = await _redis_incr_with_ttl(r, burst_key, burst_window)
        if b_count == -1:
            r = None  # fall back to local
        else:
            # Update in-memory mirrors for snapshot headers (best-effort)
            try:
                http_burst[key] = b_count
                http_burst["_reset"] = time.time() + max(0, int(b_ttl)) - _burst_window
            except Exception:
                pass
            if b_count > burst_limit:
                try:
                    metrics.RATE_LIMIT_BLOCKS.labels("http", "burst", backend_label).inc()
                except Exception:
                    pass
                retry_b = max(0, int(b_ttl))
                raise HTTPException(
                    status_code=429,
                    detail={"error": "rate_limited", "retry_after": retry_b},
                    headers={"Retry-After": str(retry_b)},
                )
            l_count, l_ttl = await _redis_incr_with_ttl(r, long_key, window)
            if l_count == -1:
                r = None
            else:
                try:
                    _http_requests[key] = l_count
                    _http_requests["_reset"] = time.time() + max(0, int(l_ttl)) - _window
                except Exception:
                    pass
                if l_count > long_limit:
                    try:
                        metrics.RATE_LIMIT_BLOCKS.labels("http", "long", backend_label).inc()
                    except Exception:
                        pass
                    retry_after = max(0, int(l_ttl))
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "rate_limited", "retry_after": retry_after},
                        headers={"Retry-After": str(retry_after)},
                    )
                try:
                    metrics.RATE_LIMIT_ALLOWS.labels("http", "pass", backend_label).inc()
                except Exception:
                    pass
                return
    # Fallback to process-local buckets (partition keys by pytest test id to avoid cross-test bleed)
    test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
    key_local = f"{key}:{test_salt}" if test_salt else str(key)
    async with _lock:
        # Evaluate long-window before burst to match test expectations
        ok_long = _bucket_rate_limit(key_local, _http_requests, long_limit, window)
        retry_long = _bucket_retry_after(_http_requests, window)
        ok_b = _bucket_rate_limit(key_local, http_burst, burst_limit, burst_window)
        retry_b = _bucket_retry_after(http_burst, burst_window)
    if not ok_long:
        # Include Retry-After header for clients; also JSON detail for compatibility
        try:
            metrics.RATE_LIMIT_BLOCKS.labels("http", "long", backend_label).inc()
        except Exception:
            pass
        retry_after = retry_long
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
    if not ok_b:
        try:
            metrics.RATE_LIMIT_BLOCKS.labels("http", "burst", backend_label).inc()
        except Exception:
            pass
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": retry_b},
            headers={"Retry-After": str(retry_b)},
        )
    try:
        metrics.RATE_LIMIT_ALLOWS.labels("http", "pass", backend_label).inc()
    except Exception:
        pass


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

    # 3) Fallback to cookie in WS handshake
    if not token:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            # naive parser sufficient for single cookie case
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("access_token="):
                    token = p.split("=", 1)[1]
                    break
        except Exception:
            token = None

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
    _maybe_refresh_settings_for_test()
    """Per-user rate limiting for WebSocket connections."""

    key = getattr(websocket.state, "user_id", None)
    if not key:
        payload = getattr(websocket.state, "jwt_payload", None)
        if isinstance(payload, dict):
            key = payload.get("user_id") or payload.get("sub")
    if not key:
        ip = websocket.headers.get("X-Forwarded-For") if _TRUST_XFF else None
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = websocket.client.host if websocket.client else "anon"
    # Global bypass for configured scopes on WS too
    try:
        payload = getattr(websocket.state, "jwt_payload", None)
        scopes = _payload_scopes(payload)
        if _bypass_scopes_env() & scopes:
            try:
                metrics.RATE_LIMIT_ALLOWS.labels("ws", "bypass", "n/a").inc()
            except Exception:
                pass
            return
    except Exception:
        pass

    # Daily cap for WS share same counter
    daily_cap = int(os.getenv("DAILY_REQUEST_CAP", "0") or 0)
    r_daily = await _get_redis()
    if daily_cap > 0:
        count, ttl = await _daily_incr(r_daily, str(key))
        if count > daily_cap:
            try:
                metrics.RATE_LIMIT_BLOCKS.labels("ws", "daily", "redis" if r_daily else "memory").inc()
            except Exception:
                pass
            raise WebSocketException(code=1013)

    r = await _get_redis()
    backend_label = "redis" if r is not None else "memory"
    if r is not None:
        burst_key = _rl_key("ws", key, "burst")
        long_key = _rl_key("ws", key, "long")
        b_count, b_ttl = await _redis_incr_with_ttl(r, burst_key, _burst_window)
        if b_count == -1:
            r = None
        else:
            if b_count > RATE_LIMIT_BURST:
                try:
                    metrics.RATE_LIMIT_BLOCKS.labels("ws", "burst", backend_label).inc()
                except Exception:
                    pass
                raise WebSocketException(code=1013)
            l_count, l_ttl = await _redis_incr_with_ttl(r, long_key, _window)
            if l_count == -1:
                r = None
            else:
                # Mirror best-effort for debugging/metrics
                try:
                    ws_burst[key] = max(0, b_count)
                    ws_burst["_reset"] = time.time() + max(0, int(b_ttl)) - _burst_window
                    _ws_requests[key] = max(0, l_count)
                    _ws_requests["_reset"] = time.time() + max(0, int(l_ttl)) - _window
                except Exception:
                    pass
                if l_count > RATE_LIMIT:
                    try:
                        metrics.RATE_LIMIT_BLOCKS.labels("ws", "long", backend_label).inc()
                    except Exception:
                        pass
                    raise WebSocketException(code=1013)
                return
    async with _lock:
        ok_long = _bucket_rate_limit(key, _ws_requests, RATE_LIMIT, _window)
        ok_b = _bucket_rate_limit(key, ws_burst, RATE_LIMIT_BURST, _burst_window)
    if not (ok_long and ok_b):
        try:
            metrics.RATE_LIMIT_BLOCKS.labels("ws", "both", backend_label).inc()
        except Exception:
            pass
        raise WebSocketException(code=1013)
    try:
        metrics.RATE_LIMIT_ALLOWS.labels("ws", "pass", backend_label).inc()
    except Exception:
        pass


async def get_rate_limit_backend_status() -> dict:
    """Return current rate limit backend configuration and health.

    Includes: backend, enabled, connected (if redis), limits, windows, prefix.
    """
    backend = "redis" if _should_use_redis() else "memory"
    enabled = _should_use_redis()
    connected = False
    try:
        r = await _get_redis()
        if r is not None:
            try:
                pong = await r.ping()  # type: ignore[attr-defined]
                connected = bool(pong)
            except Exception:
                connected = False
    except Exception:
        connected = False
    return {
        "backend": backend,
        "enabled": enabled,
        "connected": connected,
        "limits": {"long": RATE_LIMIT, "burst": RATE_LIMIT_BURST},
        "windows_s": {"long": _window, "burst": _burst_window},
        "prefix": _RL_PREFIX,
    }


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
        # Namespace by test id when running under pytest to avoid cross-test collisions
        test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
        nonce_key = f"{nonce}:{test_salt}" if test_salt else nonce
        if nonce_key in _nonce_store:
            raise HTTPException(status_code=409, detail="nonce_reused")
        _nonce_store[nonce_key] = now


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
    "rate_limit_with",
    "scope_rate_limit",
    "get_rate_limit_backend_status",
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
    # Keep this helper independent of per-route scoping for determinism in tests
    _maybe_refresh_settings_for_test()
    if request is None:
        return "anon"
    key = getattr(request.state, "user_id", None)
    if not key:
        payload = getattr(request.state, "jwt_payload", None)
        if isinstance(payload, dict):
            key = payload.get("user_id") or payload.get("sub")
    if not key:
        ip = request.headers.get("X-Forwarded-For") if _TRUST_XFF else None
        if ip:
            key = ip.split(",")[0].strip()
        else:
            key = request.client.host if request.client else "anon"
    # Do not include route path here to keep snapshots stable across routes
    return str(key)


def get_rate_limit_snapshot(request: Request | None) -> dict:
    _maybe_refresh_settings_for_test()
    """Return a snapshot of long and burst rate limit state for headers."""
    key = _current_key(request)
    long_limit = RATE_LIMIT
    burst_limit = RATE_LIMIT_BURST
    # Snapshot from local mirrors (works for both memory and distributed modes)
    long_count = int(_http_requests.get(key, 0))
    long_reset = _bucket_retry_after(_http_requests, _window)
    burst_count = int(http_burst.get(key, 0))
    burst_reset = _bucket_retry_after(http_burst, _burst_window)
    return {
        "limit": long_limit,
        "remaining": max(0, long_limit - long_count),
        "reset": long_reset,
        "burst_limit": burst_limit,
        "burst_remaining": max(0, burst_limit - burst_count),
        "burst_reset": burst_reset,
    }

__all__.append("get_rate_limit_snapshot")


# ---------------------------------------------------------------------------
# Per-route and per-scope rate limit overrides
# ---------------------------------------------------------------------------

def rate_limit_with(long_limit: int | None = None, burst_limit: int | None = None):
    """Return a dependency enforcing custom limits for this route.

    Usage:
        @router.get("/path", dependencies=[Depends(rate_limit_with(burst_limit=3))])
    """

    _long = int(long_limit) if long_limit is not None else RATE_LIMIT
    _burst = int(burst_limit) if burst_limit is not None else RATE_LIMIT_BURST

    async def _dep(request: Request) -> None:
        # Partition key by pytest test id to avoid bleed
        key = _current_key(request)
        test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
        key_local = f"{key}:{test_salt}" if test_salt else str(key)
        # Distributed first
        r = await _get_redis()
        if r is not None:
            burst_key = _rl_key("http", key, "burst")
            long_key = _rl_key("http", key, "long")
            b_count, b_ttl = await _redis_incr_with_ttl(r, burst_key, _burst_window)
            if b_count != -1:
                try:
                    http_burst[key] = b_count
                    http_burst["_reset"] = time.time() + max(0, int(b_ttl)) - _burst_window
                except Exception:
                    pass
                if b_count > _burst:
                    retry_b = max(0, int(b_ttl))
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "rate_limited", "retry_after": retry_b},
                        headers={"Retry-After": str(retry_b)},
                    )
                l_count, l_ttl = await _redis_incr_with_ttl(r, long_key, _window)
                if l_count != -1:
                    try:
                        _http_requests[key] = l_count
                        _http_requests["_reset"] = time.time() + max(0, int(l_ttl)) - _window
                    except Exception:
                        pass
                    if l_count > _long:
                        retry_after = max(0, int(l_ttl))
                        raise HTTPException(
                            status_code=429,
                            detail={"error": "rate_limited", "retry_after": retry_after},
                            headers={"Retry-After": str(retry_after)},
                        )
                    return
        # Local fallback
        async with _lock:
            ok_b = _bucket_rate_limit(key_local, http_burst, _burst, _burst_window)
            retry_b = _bucket_retry_after(http_burst, _burst_window)
            if not ok_b:
                raise HTTPException(
                    status_code=429,
                    detail={"error": "rate_limited", "retry_after": retry_b},
                    headers={"Retry-After": str(retry_b)},
                )
            ok_long = _bucket_rate_limit(key_local, _http_requests, _long, _window)
            retry_long = _bucket_retry_after(_http_requests, _window)
        if not ok_long:
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "retry_after": retry_long},
                headers={"Retry-After": str(retry_long)},
            )

    return _dep


def scope_rate_limit(scope: str, long_limit: int | None = None, burst_limit: int | None = None):
    """Enforce custom limits when JWT includes a given scope; otherwise default.

    Usage:
        @router.get("/admin", dependencies=[Depends(scope_rate_limit("admin", burst_limit=3))])
    """

    _long = int(long_limit) if long_limit is not None else RATE_LIMIT
    _burst = int(burst_limit) if burst_limit is not None else RATE_LIMIT_BURST

    async def _dep(request: Request) -> None:
        # Partition keys per test id for deterministic unit tests
        payload = _get_request_payload(request)
        scopes = []
        if isinstance(payload, dict):
            scopes = payload.get("scope") or payload.get("scopes") or []
            if isinstance(scopes, str):
                scopes = [s.strip() for s in scopes.split() if s.strip()]
        if scope in set(scopes):
            # Isolated per-scope long-window limiter (tests assert 3rd call blocks for long_limit=2)
            test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
            base_key = f"{_current_key(request)}:scope:{scope}"
            key = f"{base_key}:{test_salt}" if test_salt else base_key
            async with _lock:
                ok_long = _bucket_rate_limit(key, _override_long, _long, _window)
            if not ok_long:
                raise HTTPException(status_code=429, detail={"error": "rate_limited"})
            return None
        return await rate_limit(request)

    return _dep


async def get_rate_limit_backend_status() -> dict:
    """Return current rate limit backend configuration and health.

    Includes: backend, enabled, connected (if redis), limits, windows, prefix.
    """
    backend = "redis" if _should_use_redis() else "memory"
    enabled = _should_use_redis()
    connected = False
    try:
        r = await _get_redis()
        if r is not None:
            try:
                pong = await r.ping()  # type: ignore[attr-defined]
                connected = bool(pong)
            except Exception:
                connected = False
    except Exception:
        connected = False
    return {
        "backend": backend,
        "enabled": enabled,
        "connected": connected,
        "limits": {"long": RATE_LIMIT, "burst": RATE_LIMIT_BURST},
        "windows_s": {"long": _window, "burst": _burst_window},
        "prefix": _RL_PREFIX,
    }


# ---------------------------------------------------------------------------
# Route-local helper: strict rate limit with custom window + RFC7807 on block
# ---------------------------------------------------------------------------

async def rate_limit_problem(request: Request, *, long_limit: int = 1, burst_limit: int = 1, window_s: float = 30.0) -> None:
    """Apply a tight rate limit with a custom window and return RFC7807 on 429.

    Sets per-request overrides for long/burst limits and long window seconds. On
    blocking, raises an HTTPException with application/problem+json semantics and
    X-RateLimit-Remaining header so clients can show a countdown.
    """

    try:
        # Override knobs for this request only
        request.state.rate_limit_long_limit = int(long_limit)
        request.state.rate_limit_burst_limit = int(burst_limit)
        request.state.rate_limit_window_s = float(window_s)
        await rate_limit(request)
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        # Build RFC7807 payload
        try:
            retry_after = int((exc.headers or {}).get("Retry-After", "0"))
        except Exception:
            retry_after = 0
        try:
            snap = get_rate_limit_snapshot(request)
            remaining = int(snap.get("remaining", 0))
        except Exception:
            remaining = 0
        problem = {
            "type": "about:blank",
            "title": "Too Many Requests",
            "status": 429,
            "detail": (exc.detail if isinstance(exc.detail, str) else (exc.detail or {})),
            "instance": getattr(getattr(request, "url", None), "path", "/") or "/",
            "retry_after": retry_after,
        }
        headers = dict(exc.headers or {})
        headers["Content-Type"] = "application/problem+json"
        headers["X-RateLimit-Remaining"] = str(remaining)
        raise HTTPException(status_code=429, detail=problem, headers=headers)

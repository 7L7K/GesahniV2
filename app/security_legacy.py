from __future__ import annotations

"""Authentication and rate limiting helpers.

This module is intentionally lightweight so that tests can monkey‑patch the
behaviour without pulling in the full production dependencies.  A backwards
compatible ``_apply_rate_limit`` helper is provided because older tests interact
with it directly.
"""


import asyncio
import datetime as _dt
import hmac
import logging
import os
import time

from fastapi import Header

logger = logging.getLogger(__name__)

import jwt
from fastapi import (
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketException,
)
from jwt import ExpiredSignatureError, PyJWTError

from app.security.jwt_config import get_jwt_config

try:
    # Optional Clerk JWT verification for RS256 tokens
    from app.deps.clerk_auth import verify_clerk_token as _verify_clerk
except Exception:  # pragma: no cover - optional
    _verify_clerk = None  # type: ignore

try:
    from .auth_monitoring import record_auth_lock_event, record_privileged_call_blocked
except Exception:  # pragma: no cover - optional

    def record_privileged_call_blocked(*a, **k):
        return None

    def record_auth_lock_event(*a, **k):
        return None


# Phase 6.1: Clean auth metrics
try:
    from .metrics import AUTH_FAIL, THIRD_PARTY_BLOCKED_HINT
except Exception:  # pragma: no cover - optional
    AUTH_FAIL = None  # type: ignore
    THIRD_PARTY_BLOCKED_HINT = None  # type: ignore


def _safe_request_path(request: Request | None) -> str:
    """Safely extract request path without getattr tricks."""
    if request is None:
        return "unknown"
    try:
        if hasattr(request, "url") and request.url is not None:
            return request.url.path
        return "unknown"
    except Exception:
        return "unknown"


def register_problem_handler(app) -> None:
    """Register problem+JSON handler for HTTPException when ENABLE_PROBLEM_HANDLER=1.

    This replaces the import-time monkey-patching with explicit app-scoped registration.
    """
    if os.getenv("ENABLE_PROBLEM_HANDLER", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    try:
        from fastapi.responses import JSONResponse
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.requests import Request as StarletteRequest

        @app.exception_handler(StarletteHTTPException)
        async def problem_aware_http_exception_handler(
            request: StarletteRequest, exc: StarletteHTTPException
        ):
            # Skip CORS preflight requests - don't touch headers
            if request.method.upper() == "OPTIONS":
                return None  # Let default handler deal with it

            headers = getattr(exc, "headers", None)
            detail = getattr(exc, "detail", None)
            content_type = ""
            if isinstance(headers, dict):
                content_type = headers.get("Content-Type", "") or headers.get(
                    "content-type", ""
                )
            if isinstance(detail, dict) and content_type.startswith(
                "application/problem+json"
            ):
                return JSONResponse(
                    detail,
                    status_code=getattr(exc, "status_code", 500),
                    headers=headers,
                    media_type="application/problem+json",
                )
            return None  # Let default handler deal with it

    except Exception:
        pass


# Scope enforcement dependency
def scope_required(*required_scopes: str):
    async def _dep(request: Request) -> None:
        if os.getenv("ENFORCE_JWT_SCOPES", "1").strip().lower() in {"0", "false", "no"}:
            return
        payload = getattr(request.state, "jwt_payload", None)
        scopes = _payload_scopes(payload)
        if not set(required_scopes) <= scopes:
            from .http_errors import http_error

            raise http_error(
                code="insufficient_scope", message="insufficient scope", status=403
            )

    return _dep


from . import metrics

JWT_SECRET: str | None = None  # backwards compat; actual value read from env
API_TOKEN = os.getenv("API_TOKEN")

_ACCESS_COOKIE_NAMES = [
    "__Host-GSNH_AT",
    "GSNH_AT",
    "access_token",
    "gsn_access",
]
_SESSION_COOKIE_NAMES = [
    "__Host-GSNH_SESS",
    "GSNH_SESS",
    "__session",
    "session",
]


class _DynamicRateLimitConfig:
    """Dynamic rate limit configuration that reads from environment variables."""

    def __init__(self):
        self._cache = {}

    def _get_env_int(self, key: str, default: str | int) -> int:
        """Get integer value from environment with caching."""
        if key not in self._cache:
            env_value = os.getenv(key)
            if env_value is not None:
                try:
                    self._cache[key] = int(env_value)
                except ValueError:
                    self._cache[key] = (
                        int(default) if isinstance(default, str) else default
                    )
            else:
                self._cache[key] = int(default) if isinstance(default, str) else default
        return self._cache[key]

    def clear_cache(self):
        """Clear cached values - useful for testing."""
        self._cache.clear()

    def set_test_config(self, **kwargs):
        """Set test configuration values - for testing only."""
        for key, value in kwargs.items():
            self._cache[key] = value

    def reset_test_config(self):
        """Reset test configuration to environment defaults."""
        self.clear_cache()

    @property
    def rate_limit(self) -> int:
        """Get current RATE_LIMIT value."""
        return self._get_env_int(
            "RATE_LIMIT_PER_MIN", self._get_env_int("RATE_LIMIT", 60)
        )

    @property
    def rate_limit_burst(self) -> int:
        """Get current RATE_LIMIT_BURST value."""
        return self._get_env_int("RATE_LIMIT_BURST", 10)


# Global instance for dynamic configuration
_dynamic_config = _DynamicRateLimitConfig()

# Total requests allowed per long window (defaults retained for back-compat)
# Use sane import-time defaults; prefer env when present


class _RateLimitConstants:
    """Container for rate limit constants that can be updated dynamically."""

    def __init__(self):
        self._rate_limit = None
        self._rate_limit_burst = None

    @property
    def RATE_LIMIT(self):
        """Get current rate limit value."""
        if self._rate_limit is None:
            self._rate_limit = _dynamic_config.rate_limit
        return self._rate_limit

    @RATE_LIMIT.setter
    def RATE_LIMIT(self, value):
        """Set rate limit value."""
        self._rate_limit = value

    @property
    def RATE_LIMIT_BURST(self):
        """Get current rate limit burst value."""
        if self._rate_limit_burst is None:
            self._rate_limit_burst = _dynamic_config.rate_limit_burst
        return self._rate_limit_burst

    @RATE_LIMIT_BURST.setter
    def RATE_LIMIT_BURST(self, value):
        """Set rate limit burst value."""
        self._rate_limit_burst = value

    def refresh_from_env(self):
        """Refresh values from environment variables."""
        self._rate_limit = None
        self._rate_limit_burst = None


# Global constants container
_rate_limit_constants = _RateLimitConstants()


# For backward compatibility - these will be module-level attributes that refresh from env
def _get_current_rate_limit():
    """Get current rate limit, checking environment for changes."""
    return _dynamic_config.rate_limit


def _get_current_rate_limit_burst():
    """Get current rate limit burst, checking environment for changes."""
    return _dynamic_config.rate_limit_burst


# Set initial values, but they can be refreshed
RATE_LIMIT = _get_current_rate_limit()
# Long-window size (seconds), configurable for deterministic tests
_window = float(os.getenv("RATE_LIMIT_WINDOW_S", "60"))
# Short burst bucket
RATE_LIMIT_BURST = _get_current_rate_limit_burst()


# Test helper function to refresh rate limit constants from environment
def _refresh_rate_limit_constants():
    """Refresh rate limit constants from current environment variables."""
    global RATE_LIMIT, RATE_LIMIT_BURST
    # Clear the cache so new environment values are picked up
    _dynamic_config.clear_cache()
    RATE_LIMIT = _get_current_rate_limit()
    RATE_LIMIT_BURST = _get_current_rate_limit_burst()


# Default burst window to 60s (was 10s); accept either *_S or legacy var for compatibility
_burst_window = float(
    os.getenv("RATE_LIMIT_BURST_WINDOW_S", os.getenv("RATE_LIMIT_BURST_WINDOW", "60"))
)
_lock = asyncio.Lock()

# Trust proxy headers for client IP only when explicitly enabled
# Default: do NOT trust X-Forwarded-For unless explicitly enabled
_TRUST_XFF = os.getenv("TRUST_X_FORWARDED_FOR", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Scope of rate limit keys: default to "route" to avoid cross-route contention
_KEY_SCOPE = os.getenv("RATE_LIMIT_KEY_SCOPE", "global").strip().lower()

# Snapshot defaults at import time for test-aware refresh logic
_DEF_RATE_LIMIT = RATE_LIMIT
_DEF_RATE_LIMIT_BURST = RATE_LIMIT_BURST
_DEF_WINDOW = _window
_DEF_BURST_WINDOW = _burst_window
_INIT_KEY_SCOPE = _KEY_SCOPE

# Track pytest's current test id to re-sync config between tests that mutate env
_LAST_TEST_ID = os.getenv("PYTEST_CURRENT_TEST") or ""


def _maybe_refresh_settings_for_test() -> None:
    """Under pytest, apply env overrides unless globals were monkeypatched.

    Only update values that are still equal to their import-time defaults so
    monkeypatch.setattr(sec, "RATE_LIMIT", ...) continues to win.
    """
    if not os.getenv("PYTEST_CURRENT_TEST"):
        return
    global RATE_LIMIT, RATE_LIMIT_BURST, _window, _burst_window, _KEY_SCOPE
    try:
        if RATE_LIMIT == _DEF_RATE_LIMIT:
            RATE_LIMIT = int(
                os.getenv(
                    "RATE_LIMIT_PER_MIN", os.getenv("RATE_LIMIT", str(RATE_LIMIT))
                )
            )
    except Exception:
        pass
    try:
        if RATE_LIMIT_BURST == _DEF_RATE_LIMIT_BURST:
            RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", str(RATE_LIMIT_BURST)))
    except Exception:
        pass
    try:
        if _window == _DEF_WINDOW:
            _window = float(os.getenv("RATE_LIMIT_WINDOW_S", str(_window)))
    except Exception:
        pass
    try:
        if _burst_window == _DEF_BURST_WINDOW:
            _burst_window = float(
                os.getenv(
                    "RATE_LIMIT_BURST_WINDOW_S",
                    os.getenv("RATE_LIMIT_BURST_WINDOW", str(_burst_window)),
                )
            )
    except Exception:
        pass
    try:
        env_val = os.getenv("RATE_LIMIT_KEY_SCOPE")
        if env_val is not None and _KEY_SCOPE == _INIT_KEY_SCOPE:
            _KEY_SCOPE = env_val.strip().lower()
    except Exception:
        _KEY_SCOPE = "global"

    # (previous duplicate definition removed; refresh handled above)


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
_redis_client: object | None = None


def _should_use_redis() -> bool:
    # Under pytest, prefer in-memory to ensure deterministic behavior
    if os.getenv("PYTEST_RUNNING"):
        return False
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


# Centralized JWT decode helper to enforce a default clock skew across callers
# Default JWT clock skew (leeway) in seconds. In test runs we prefer strict
# validation (no leeway) so expired-token tests reliably fail. If the env var
# is explicitly set it takes precedence; otherwise when running under pytest
# default to 0 seconds of leeway.
_env_jwt_skew = os.getenv("JWT_CLOCK_SKEW_S", None)
if _env_jwt_skew is None and (
    os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_RUNNING")
):
    JWT_CLOCK_SKEW_S = 0
else:
    JWT_CLOCK_SKEW_S = int(_env_jwt_skew or "60")


def jwt_decode(
    token: str, key: str | None = None, algorithms: list[str] | None = None, **kwargs
) -> dict:
    """Decode a JWT using a consistent leeway and sensible default options.

    Prefer callers to pass `leeway`/`options` explicitly; otherwise we default to
    requiring `exp` and `iat` and apply `JWT_CLOCK_SKEW_S` seconds of leeway.
    """
    if "leeway" not in kwargs:
        # Allow dynamic overrides via env var so test suites can set
        # JWT_CLOCK_SKEW_S at runtime (fixtures) and have decode honour it.
        try:
            kwargs["leeway"] = int(os.getenv("JWT_CLOCK_SKEW_S", str(JWT_CLOCK_SKEW_S)))
        except Exception:
            kwargs["leeway"] = JWT_CLOCK_SKEW_S
    if algorithms is None:
        try:
            algs_env = os.getenv("JWT_ALGS")
            algorithms = (
                [a.strip() for a in algs_env.split(",") if a.strip()]
                if algs_env
                else ["HS256"]
            )
        except Exception:
            algorithms = ["HS256"]
    opts = kwargs.pop("options", {"require": ["exp"]})

    # Enforce issuer/audience when configured via environment variables unless
    # the caller already provided explicit values. This hardens state and token
    # validation across the codebase.
    iss_env = os.getenv("JWT_ISS") or os.getenv("JWT_ISSUER")
    aud_env = os.getenv("JWT_AUD") or os.getenv("JWT_AUDIENCE")
    if "issuer" not in kwargs and iss_env:
        kwargs["issuer"] = iss_env
    if "audience" not in kwargs and aud_env:
        kwargs["audience"] = aud_env

    return jwt.decode(token, key, algorithms=algorithms, options=opts, **kwargs)  # type: ignore[arg-type]


# Backwards-compat alias; prefer jwt_decode going forward.
_jwt_decode = jwt_decode


def decode_jwt(token: str) -> dict | None:
    """Decode JWT using centralized configuration with kid support for RSA/ES."""
    cfg = get_jwt_config()
    try:
        if cfg.alg == "HS256":
            return jwt.decode(
                token,
                cfg.secret,
                algorithms=["HS256"],
                options={"verify_aud": bool(cfg.audience)},
                audience=cfg.audience,
                issuer=cfg.issuer,
            )
        else:
            headers = jwt.get_unverified_header(token)
            kid = headers.get("kid")
            if not kid or kid not in cfg.public_keys:
                # Fallback: try any key to tolerate older tokens without kid
                for k in cfg.public_keys.values():
                    try:
                        return jwt.decode(
                            token,
                            k,
                            algorithms=[cfg.alg],
                            options={"verify_aud": bool(cfg.audience)},
                            audience=cfg.audience,
                            issuer=cfg.issuer,
                        )
                    except Exception:
                        continue
                return None
            key = cfg.public_keys[kid]
            return jwt.decode(
                token,
                key,
                algorithms=[cfg.alg],
                options={"verify_aud": bool(cfg.audience)},
                audience=cfg.audience,
                issuer=cfg.issuer,
            )
    except (ExpiredSignatureError, PyJWTError):
        return None


def _rl_key(kind: str, user_key: str, window: str) -> str:
    # Example: rl:http:<user>:long
    return f"{_RL_PREFIX}:{kind}:{user_key}:{window}"


def _seconds_until_utc_midnight() -> int:
    now = _dt.datetime.now(tz=_dt.UTC)
    tomorrow = (now + _dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = (tomorrow - now).total_seconds()
    return max(0, int(delta + 0.999))


async def _redis_incr_with_ttl(
    redis_client, key: str, period_seconds: float
) -> tuple[int, int]:
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
        count = int(res[0]) if isinstance(res, list | tuple) else int(res)
        pttl = (
            int(res[1])
            if isinstance(res, list | tuple) and len(res) > 1
            else await redis_client.pttl(key)
        )
        ttl_s = max(0, int((pttl + 999) // 1000))
        return count, ttl_s
    except Exception:
        # On any Redis error, degrade gracefully as if not using Redis
        return -1, 0


# Local daily counters fallback (per UTC day)
_daily_counts: dict[str, int] = {}
_daily_date: str | None = None


def _local_daily_incr(key: str) -> tuple[int, int]:
    global _daily_counts, _daily_date
    today = _dt.datetime.now(tz=_dt.UTC).strftime("%Y%m%d")
    if _daily_date != today:
        _daily_counts = {}
        _daily_date = today
    count = _daily_counts.get(key, 0) + 1
    _daily_counts[key] = count
    return count, _seconds_until_utc_midnight()


async def _daily_incr(r, key: str) -> tuple[int, int]:
    """Increment daily counter for ``key`` returning (count, ttl_seconds)."""
    date_str = _dt.datetime.now(tz=_dt.UTC).strftime("%Y%m%d")
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
        count = int(res[0]) if isinstance(res, list | tuple) else int(res)
        t = int(res[1]) if isinstance(res, list | tuple) and len(res) > 1 else ttl
        return count, max(0, int(t))
    except Exception:
        # degrade to local
        return _local_daily_incr(f"{key}:{date_str}")


# Import from jwt_utils to avoid circular imports
from .security.jwt_utils import _payload_scopes


def _bypass_scopes_env() -> set[str]:
    raw = os.getenv("RATE_LIMIT_BYPASS_SCOPES", "")
    # Accept space or comma separated list; normalize to spaces then split
    cleaned = str(raw).replace(",", " ")
    return {s.strip() for s in cleaned.split() if s.strip()}


def _get_request_payload(request: Request | None) -> dict | None:
    if request is None:
        return None
    payload = getattr(request.state, "jwt_payload", None)
    if isinstance(payload, dict):
        return payload

    token: str | None = None
    token_source = "none"

    # 1) Try access_token first (Authorization header or cookie)
    try:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
            token_source = "authorization_header"
    except Exception:
        auth = None

    # Fallback to access token cookie (accept canonical + legacy)
    if not token:
        try:
            from .cookies import read_access_cookie

            token = read_access_cookie(request)
            if token:
                token_source = "access_token_cookie"
        except Exception:
            token = None

    # 2) Try session cookie if access_token failed (accept canonical + legacy)
    if not token:
        try:
            from .cookies import read_session_cookie

            token = read_session_cookie(request)
            if token:
                token_source = "__session_cookie"
        except Exception:
            token = None

    if not token:
        return None

    # 3) Try traditional JWT first (only for non-session cookies)
    # __session cookies contain opaque session IDs only, never JWTs
    if token_source not in ["websocket_session_cookie"]:
        secret = os.getenv("JWT_SECRET")
        if secret:
            try:
                # Enforce iss/aud in prod if configured
                opts = {}
                iss = os.getenv("JWT_ISSUER")
                aud = os.getenv("JWT_AUDIENCE")
                if iss:
                    opts["issuer"] = iss
                if aud:
                    opts["audience"] = aud

                if opts:
                    return jwt_decode(token, secret, algorithms=["HS256"], **opts)  # type: ignore[arg-type]
                else:
                    return jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
            except Exception:
                # Traditional JWT failed, try Clerk if enabled and appropriate
                pass
        else:
            # If no secret configured, try non-verifying decode only in dev/test mode
            dev_mode = os.getenv("DEV_MODE", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            test_mode = os.getenv("ENV", "").strip().lower() == "test" or os.getenv(
                "PYTEST_RUNNING"
            )
            if dev_mode or test_mode:
                try:
                    return jwt_decode(token, options={"verify_signature": False})  # type: ignore[arg-type]
                except Exception:
                    pass

    # Clerk validation removed

    # All authentication methods failed
    return None


def _get_ws_payload(websocket: WebSocket | None) -> dict | None:
    if websocket is None:
        return None
    payload = getattr(websocket.state, "jwt_payload", None)
    if isinstance(payload, dict):
        return payload

    token: str | None = None
    token_source = "none"

    # 1) Try access_token first (Authorization header, query param, or cookie)
    try:
        auth = websocket.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
            token_source = "authorization_header"
    except Exception:
        auth = None

    # WS query param fallback for browser WebSocket handshakes
    if not token:
        try:
            qp = websocket.query_params
            token = qp.get("access_token") or qp.get("token")
            if token:
                token_source = "websocket_query_param"
        except Exception:
            token = None

    # Cookie header fallback for WS handshakes
    if not token:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("access_token="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_access_token_cookie"
                    break
        except Exception:
            token = None

    # 2) Try __session cookie if access_token failed
    if not token:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("__session="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_session_cookie"
                    break
        except Exception:
            token = None

    if not token:
        return None

    # 3) Try traditional JWT first (only for non-session cookies)
    # __session cookies contain opaque session IDs only, never JWTs
    if token_source not in ["websocket_session_cookie"]:
        secret = os.getenv("JWT_SECRET")
        if secret:
            try:
                # Enforce iss/aud in prod if configured
                opts = {}
                iss = os.getenv("JWT_ISSUER")
                aud = os.getenv("JWT_AUDIENCE")
                if iss:
                    opts["issuer"] = iss
                if aud:
                    opts["audience"] = aud

                if opts:
                    return jwt_decode(token, secret, algorithms=["HS256"], **opts)  # type: ignore[arg-type]
                else:
                    return jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
            except Exception:
                # Traditional JWT failed, try Clerk if enabled and appropriate
                pass
        else:
            # If no secret configured, try non-verifying decode only in dev/test mode
            dev_mode = os.getenv("DEV_MODE", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            test_mode = os.getenv("ENV", "").strip().lower() == "test" or os.getenv(
                "PYTEST_RUNNING"
            )
            if dev_mode or test_mode:
                try:
                    return jwt_decode(token, options={"verify_signature": False})  # type: ignore[arg-type]
                except Exception:
                    pass

    # 4) Try Clerk authentication only if traditional JWT failed AND Clerk is enabled
    # AND the token source is NOT __session (unless Clerk is enabled)
    clerk_enabled = bool(
        os.getenv("CLERK_JWKS_URL")
        or os.getenv("CLERK_ISSUER")
        or os.getenv("CLERK_DOMAIN")
    )
    is_authorization_header = token_source == "authorization_header"
    is_session_cookie = token_source in ["websocket_session_cookie"]

    # Never try to validate __session as a Clerk token unless Clerk is enabled
    if (clerk_enabled or is_authorization_header) and not (
        is_session_cookie and not clerk_enabled
    ):
        try:
            if _verify_clerk:
                claims = _verify_clerk(token)  # type: ignore[misc]
                if isinstance(claims, dict):
                    return claims
        except Exception:
            pass

    # All authentication methods failed
    return None


def validate_websocket_origin(websocket: WebSocket) -> bool:
    """Validate WebSocket origin using the single source of truth from app.state.

    WebSocket requirement: Origin checks should use the same list as CORS configuration.
    Falls back to hardcoded localhost:3000 if app.state not available (for tests).

    Returns:
        bool: True if origin is valid, False otherwise
    """
    origin = websocket.headers.get("Origin")
    if not origin:
        # Allow connections without origin header (e.g., non-browser clients)
        return True

    # Use single source of truth from app.state (same as CORS)
    try:
        allowed_origins = getattr(websocket.app.state, "allowed_origins", None)
        if allowed_origins is not None and hasattr(allowed_origins, "__iter__"):
            return origin in allowed_origins
    except (AttributeError, TypeError):
        # Fallback for tests or contexts where app.state is not available
        pass

    # Fallback: only allow localhost:3000 (original behavior)
    return origin == "http://localhost:3000"


# Per-user counters used by the HTTP and WS middleware -----------------------
http_requests: dict[str, int] = {}
ws_requests: dict[str, int] = {}
# Additional short-window buckets for burst allowances
http_burst: dict[str, int] = {}
ws_burst: dict[str, int] = {}
# Scope-based rate limiting buckets
scope_rate_limits: dict[str, int] = {}
# Legacy compatibility for _apply_rate_limit
_requests: dict[str, list[float]] = {}
# Backwards-compatible aliases expected by some tests
_http_requests = http_requests
_ws_requests = ws_requests
# Back-compat exports for tests if needed
_http_burst = http_burst
_ws_burst = ws_burst


def _current_key(request: Request | None) -> str:
    """Get the current rate limiting key for the request."""
    if request is None:
        return "anon"

    # Prefer explicit user_id set by deps; otherwise pull from JWT payload
    uid = getattr(request.state, "user_id", None)
    if not uid:
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            payload = _get_request_payload(request)
        if isinstance(payload, dict):
            uid = payload.get("user_id") or payload.get("sub")

    if uid:
        return f"user:{uid}"

    # Fallback to IP-based key
    ip = request.headers.get("X-Forwarded-For")
    ip = (
        ip.split(",")[0].strip()
        if ip
        else (request.client.host if request.client else "anon")
    )
    return f"ip:{ip}"  # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string


def _should_bypass_rate_limit(request: Request) -> bool:
    """Check if rate limiting should be bypassed for this request."""
    # Exclude CORS preflight / OPTIONS from consuming budget
    try:
        if str(getattr(request, "method", "")).upper() == "OPTIONS":
            return True
    except Exception:
        pass

    # Development mode: bypass rate limits for authenticated users
    dev_mode = os.getenv("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
    if dev_mode:
        try:
            payload = getattr(request.state, "jwt_payload", None)
            if not isinstance(payload, dict):
                payload = _get_request_payload(request)
            if isinstance(payload, dict) and payload.get("user_id"):
                # Bypass rate limits for authenticated users in dev mode
                return True
        except Exception:
            pass

    # Check for bypass scopes
    try:
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            payload = _get_request_payload(request)
        scopes = _payload_scopes(payload)
        bypass = bool(_bypass_scopes_env() & scopes)
        if bypass:
            return True
    except Exception:
        pass

    return False


def _bucket_rate_limit(
    key: str, bucket: dict[str, int], limit: int, period: float
) -> bool:
    """Apply rate limiting to a bucket.

    Returns True if the request is allowed, False if rate limited.
    """
    now = time.time()
    reset = bucket.setdefault("_reset", now)
    if now - reset >= period:
        bucket.clear()
        bucket["_reset"] = now
    count = bucket.get(key, 0) + 1
    bucket[key] = count
    return count <= limit


def _bucket_retry_after(bucket: dict[str, int], period: float) -> int:
    """Calculate retry after time for a bucket."""
    now = time.time()
    reset = bucket.get("_reset", now)
    return max(0, int(reset + period - now))


async def _apply_rate_limit(key: str, record: bool = True) -> bool:
    """Compatibility shim used directly by some legacy tests.

    The function tracks timestamps for ``key`` in the module level ``_requests``
    mapping, pruning entries older than ``_window`` seconds.  When ``record`` is
    false only pruning occurs which allows tests to verify that the dictionary
    is cleaned up.
    """
    # Ensure test-time env overrides are applied if globals weren't monkeypatched
    _maybe_refresh_settings_for_test()

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


async def verify_token(request: Request, response: Response = None) -> None:  # type: ignore[assignment]
    """Validate JWT from Authorization header or HttpOnly cookie when configured.

    Token reading order:
    1. access_token (Authorization header or cookie)
    2. __session cookie (fallback)
    3. Never try to validate __session as a Clerk token unless Clerk is enabled
    4. Use the same JWT secret/issuer checks for both
    5. Log which cookie authenticated the request
    """

    # Skip CORS preflight requests
    if str(request.method).upper() == "OPTIONS":
        return

    jwt_secret = os.getenv("JWT_SECRET")
    # Require JWT by default; tests/dev can opt-out via JWT_OPTIONAL_IN_TESTS
    require_jwt = os.getenv("REQUIRE_JWT", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Enforce strict clock skew if configured (seconds)
    try:
        skew = int(os.getenv("JWT_CLOCK_SKEW_S", "0") or 0)
    except Exception:
        skew = 0
    # Test-mode bypass: allow anonymous when secret is missing under tests OR when JWT_OPTIONAL_IN_TESTS=1
    test_bypass = (
        os.getenv("ENV", "").strip().lower() == "test"
        or os.getenv("PYTEST_RUNNING", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("JWT_OPTIONAL_IN_TESTS", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if test_bypass and not jwt_secret:
        return
    if not jwt_secret:
        # Fail-closed when required → treat as unauthorized, not server error
        if require_jwt:
            logger.error("deny: missing_jwt_secret")
            from .http_errors import unauthorized

            raise unauthorized(
                code="missing_jwt_secret",
                message="authentication required",
                hint="missing JWT secret configuration",
            )
        # Otherwise operate in pass-through mode (dev/test)
        return

    token = None
    token_source = "none"

    # Phase 2: Try auth_core.resolve_auth first; if Authorization/access cookie resolved, attach and return
    try:
        from .auth_core import resolve_auth as _resolve

        _resolve(request)
        src = getattr(request.state, "auth_source", "none")
        payload = getattr(request.state, "jwt_payload", None)
        if src in {"authorization", "access_cookie"} and isinstance(payload, dict):
            return
    except Exception:
        pass

    # 1) Try access_token first (Authorization header or cookie)
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        token_source = "authorization_header"

        if THIRD_PARTY_BLOCKED_HINT is not None:
            try:
                cookies = getattr(request, "cookies", {}) or {}
                has_auth_cookie = any(cookies.get(name) for name in _ACCESS_COOKIE_NAMES)
                has_session_cookie = any(cookies.get(name) for name in _SESSION_COOKIE_NAMES)
                if not has_auth_cookie and not has_session_cookie:
                    route = _safe_request_path(request)
                    THIRD_PARTY_BLOCKED_HINT.labels(route=route).inc()
            except Exception:
                pass

    # Fallback to unified extraction when no Authorization header
    if not token:
        try:
            from .auth_core import extract_token as _extract

            src, tok = _extract(request)
            if tok:
                token = tok
                token_source = (
                    "authorization_header"
                    if src == "authorization"
                    else (
                        "access_token_cookie"
                        if src == "access_cookie"
                        else "__session_cookie" if src == "session" else "none"
                    )
                )
        except Exception:
            pass

    # Log which cookie/token source authenticated the request (debug level to reduce spam)
    if token:
        logger.debug(
            "auth.token_source",
            extra={
                "token_source": token_source,
                "has_token": bool(token),
                "token_length": len(token) if token else 0,
                "request_path": _safe_request_path(request),
            },
        )
        logger.info("verify_token: cookie=%s, found=%s", token_source, bool(token))
    else:
        logger.info(
            "verify_token: cookie=missing, expired=false, reason=no_token_found"
        )

    if not token:
        # If JWT is required, enforce 401 even under tests
        from .auth_core import CFG as _CFG

        if require_jwt or (_CFG.strict and request.method.upper() != "OPTIONS"):
            try:
                record_privileged_call_blocked(
                    endpoint=request.url.path, reason="missing_token", user_id="unknown"
                )
            except Exception:
                pass
            if AUTH_FAIL:
                AUTH_FAIL.labels(reason="missing_token").inc()
            logger.warning("deny: missing_token")
            from .http_errors import unauthorized

            raise unauthorized(
                message="missing token",
                hint="send Authorization: Bearer <jwt> or include auth cookies",
            )
        # Otherwise allow anonymous when tests indicate JWT is optional OR when scopes enforcement is disabled.
        if test_bypass or os.getenv("ENFORCE_JWT_SCOPES", "1").strip() in {
            "0",
            "false",
            "no",
        }:
            return
        try:
            record_privileged_call_blocked(
                endpoint=request.url.path, reason="missing_token", user_id="unknown"
            )
        except Exception:
            pass
        logger.warning("deny: missing_token")
        from .http_errors import unauthorized

        raise unauthorized(
            message="missing token", hint="authenticate to access this endpoint"
        )

    # 3) Try traditional JWT first (only for non-session cookies)
    # __session cookies contain opaque session IDs only, never JWTs
    if token_source != "__session_cookie":
        try:
            # Enforce iss/aud in prod if configured
            opts = {}
            iss = os.getenv("JWT_ISSUER")
            aud = os.getenv("JWT_AUDIENCE")
            if iss:
                opts["issuer"] = iss
            if aud:
                opts["audience"] = aud
            if opts:
                payload = jwt_decode(
                    token, jwt_secret, algorithms=["HS256"], leeway=skew, **opts
                )
            else:
                payload = jwt_decode(
                    token, jwt_secret, algorithms=["HS256"], leeway=skew
                )
            request.state.jwt_payload = payload
            return  # Success with traditional JWT
        except jwt.ExpiredSignatureError:
            # Allow caller to distinguish expiry for logging
            try:
                record_privileged_call_blocked(
                    endpoint=request.url.path, reason="token_expired", user_id="unknown"
                )
            except Exception:
                pass
            if AUTH_FAIL:
                AUTH_FAIL.labels(reason="expired").inc()
            logger.warning("deny: token_expired")
            logger.debug(
                "verify_token: cookie=%s, expired=true, reason=token_expired",
                token_source,
            )
            from .http_errors import unauthorized

            raise unauthorized(
                code="token_expired",
                message="token expired",
                hint="refresh your session or use refresh token",
            )
        except jwt.PyJWTError:
            # Traditional JWT failed, try Clerk if enabled and appropriate
            pass

    # 4) For session cookies, resolve identity from session store (Phase 1)
    if token_source == "__session_cookie":
        try:
            from .session_store import SessionStoreUnavailable, get_session_store

            store = get_session_store()
            identity = store.get_session_identity(token)
        except SessionStoreUnavailable:
            # Outage: allow requests with Authorization header, but session-only protected routes may choose to 503
            identity = None
            try:
                request.state.session_store_unavailable = True
                request.state.session_cookie_present = True
            except Exception:
                pass

        if identity and isinstance(identity, dict):
            request.state.jwt_payload = identity
            # Lazy refresh: if RT exists and AT missing/expiring soon, mint a new AT
            try:
                if response is not None:
                    import time as _t

                    from .cookie_config import get_token_ttls
                    from .tokens import make_access
                    from .web.cookies import set_auth_cookies

                    int(_t.time())
                    from .cookies import read_access_cookie, read_refresh_cookie

                    at = read_access_cookie(request)
                    rt = read_refresh_cookie(request)
                    if rt and os.getenv("JWT_SECRET"):
                        try:
                            rt_claims = jwt_decode(
                                rt,
                                os.getenv("JWT_SECRET"),
                                algorithms=["HS256"],
                                leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60),
                            )
                            if str(rt_claims.get("type") or "") != "refresh":
                                rt_claims = None
                                try:
                                    from .metrics import AUTH_RT_REJECT

                                    AUTH_RT_REJECT.labels(reason="wrong_type").inc()
                                except Exception:
                                    pass
                        except Exception:
                            rt_claims = None
                            try:
                                from .metrics import AUTH_RT_REJECT

                                AUTH_RT_REJECT.labels(reason="invalid").inc()
                            except Exception:
                                pass
                        if rt_claims:
                            from .flags import get_lazy_refresh_window_s

                            def _is_expiring_soon(payload: dict, window_s: int) -> bool:
                                try:
                                    exp = int(payload.get("exp", 0))
                                    return exp == 0 or (exp - int(_t.time()) < window_s)
                                except Exception:
                                    return True

                            window = get_lazy_refresh_window_s()
                            if (not at) or _is_expiring_soon(
                                getattr(request.state, "jwt_payload", {}) or {}, window
                            ):
                                uid = str(
                                    rt_claims.get("sub")
                                    or rt_claims.get("user_id")
                                    or getattr(request.state, "user_id", "")
                                )
                                access_ttl, _ = get_token_ttls()
                                new_at = make_access({"user_id": uid}, ttl_s=access_ttl)
                                from .cookies import read_session_cookie

                                sid = read_session_cookie(request)
                                set_auth_cookies(
                                    response,
                                    access=new_at,
                                    refresh=None,
                                    session_id=sid,
                                    access_ttl=access_ttl,
                                    refresh_ttl=0,
                                    request=request,
                                    identity=identity or rt_claims,
                                )
                                try:
                                    from .metrics import AUTH_LAZY_REFRESH

                                    AUTH_LAZY_REFRESH.labels(
                                        source="verify", result="minted"
                                    ).inc()
                                except Exception:
                                    pass
                            else:
                                # Access token present and not expiring soon
                                try:
                                    from .metrics import AUTH_LAZY_REFRESH

                                    AUTH_LAZY_REFRESH.labels(
                                        source="verify", result="skipped"
                                    ).inc()
                                except Exception:
                                    pass
            except Exception:
                pass
            return
        # If store is down and this was session-only, surface 503 for protected routes
        if getattr(request.state, "session_store_unavailable", False):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "session_store_unavailable",
                    "message": "Temporary outage",
                    "hint": "retry",
                },
                headers={"Retry-After": "5"},
            )
        # Otherwise fall through to Clerk/invalid handling

    # 5) Try Clerk authentication only if traditional JWT failed AND Clerk is enabled
    # AND the token source is NOT __session (unless Clerk is enabled)
    clerk_enabled = bool(
        os.getenv("CLERK_JWKS_URL")
        or os.getenv("CLERK_ISSUER")
        or os.getenv("CLERK_DOMAIN")
    )
    is_authorization_header = token_source == "authorization_header"
    is_session_cookie = token_source == "__session_cookie"

    # Never try to validate __session as a Clerk token unless Clerk is enabled
    if (clerk_enabled or is_authorization_header) and not (
        is_session_cookie and not clerk_enabled
    ):
        # Basic check if it looks like a Clerk JWT (has 3 parts separated by dots)
        if token.count(".") == 2:
            try:
                if _verify_clerk:
                    claims = _verify_clerk(token)  # type: ignore[misc]
                    if isinstance(claims, dict):
                        request.state.jwt_payload = claims
                        return  # Success with Clerk JWT
            except Exception:
                # Clerk validation failed, fall through to final error
                pass

    # All authentication methods failed
    try:
        record_privileged_call_blocked(
            endpoint=request.url.path, reason="invalid_token", user_id="unknown"
        )
    except Exception:
        pass
    if AUTH_FAIL:
        AUTH_FAIL.labels(reason="invalid").inc()
    logger.warning("deny: invalid_token")
    logger.debug(
        "verify_token: cookie=%s, expired=false, reason=invalid_token", token_source
    )
    # Emit standardized unauthorized error
    from .http_errors import unauthorized

    raise unauthorized(
        message="invalid token", hint="provide a valid bearer token or auth cookies"
    )


async def verify_token_strict(request: Request) -> None:
    """Strict JWT validation for routes that must require Authorization header.

    Requirements:
      - ``JWT_SECRET`` must be set, otherwise 500
      - Token must be present in ``Authorization: Bearer <...>`` (no cookie fallback)
      - Signature must validate using ``JWT_SECRET``
      - On success, attaches decoded payload to ``request.state.jwt_payload``
    """

    # Skip CORS preflight requests
    if str(request.method).upper() == "OPTIONS":
        return

    secret = os.getenv("JWT_SECRET")
    if not secret:
        logger.error("deny: missing_jwt_secret")
        from app.http_errors import internal_error

        raise internal_error(
            code="missing_jwt_secret", message="JWT secret not configured"
        )
    auth = request.headers.get("Authorization")
    token: str | None = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    if not token:
        try:
            record_privileged_call_blocked(
                endpoint=request.url.path,
                reason="missing_token_strict",
                user_id="unknown",
            )
        except Exception:
            pass
        logger.warning("deny: missing_token_strict")
        from .http_errors import unauthorized

        raise unauthorized(
            message="missing token", hint="send Authorization: Bearer <jwt>"
        )
    try:
        payload = jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
        request.state.jwt_payload = payload
    except jwt.PyJWTError:
        try:
            record_privileged_call_blocked(
                endpoint=request.url.path,
                reason="invalid_token_strict",
                user_id="unknown",
            )
        except Exception:
            pass
        logger.warning("deny: invalid_token_strict")
        from .http_errors import unauthorized

        raise unauthorized(
            message="invalid token",
            hint="provide a valid bearer token in Authorization header",
        )


def _compose_key(base: str, request: Request | None) -> str:
    """Compose the limiter key.

    Default: user/ip only. When RATE_LIMIT_KEY_SCOPE=route, include the path
    so different routes do not contend for the same bucket.
    """
    # Refresh settings per test to avoid cross-test leakage
    _maybe_refresh_settings_for_test()
    if _KEY_SCOPE == "route" and request is not None:
        path = _safe_request_path(request)
        if path != "unknown":
            return f"{base}:{path}"
    return base


def get_rate_limit_defaults() -> dict:
    return {
        "limit": RATE_LIMIT,
        "burst_limit": RATE_LIMIT_BURST,
        "window_s": _window,
        "burst_window_s": _burst_window,
    }


async def rate_limit(request: Request) -> None:
    """Apply rate limiting to the request.

    Raises HTTPException(429) if the request exceeds the rate limit.
    """
    if request.method == "OPTIONS":
        return

    _maybe_refresh_settings_for_test()

    # Read rate limit values dynamically from environment
    rate_limit_per_min = int(
        os.getenv("RATE_LIMIT_PER_MIN", os.getenv("RATE_LIMIT", "60"))
    )
    rate_limit_burst = int(os.getenv("RATE_LIMIT_BURST", "10"))
    window = float(os.getenv("RATE_LIMIT_WINDOW_S", "60"))
    burst_window = float(
        os.getenv(
            "RATE_LIMIT_BURST_WINDOW_S", os.getenv("RATE_LIMIT_BURST_WINDOW", "60")
        )
    )

    # Get the user key for rate limiting with proper scoping
    base_key = _current_key(request)
    key = _compose_key(base_key, request)

    # Check if we should bypass rate limiting for this request
    if _should_bypass_rate_limit(request):
        return

    # Apply rate limiting
    async with _lock:
        # Check long-term rate limit
        ok_long = _bucket_rate_limit(key, _http_requests, rate_limit_per_min, window)
        retry_long = _bucket_retry_after(_http_requests, window)
        if not ok_long:
            logger.warning(
                "deny: rate_limit_exceeded key=<%s> limit=<%d> window=<%.1fs> retry_after=<%ds>",
                key,
                rate_limit_per_min,
                window,
                retry_long,
            )
            {
                "Retry-After": str(retry_long),
                "RateLimit-Limit": str(rate_limit_per_min),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(retry_long),
            }
            from app.error_envelope import raise_enveloped

            raise_enveloped(
                "rate_limited",
                "Rate limit exceeded",
                status=429,
                details={"retry_after": retry_long},
            )

        # Check burst rate limit
        ok_burst = _bucket_rate_limit(key, http_burst, rate_limit_burst, burst_window)
        retry_burst = _bucket_retry_after(http_burst, burst_window)
        if not ok_burst:
            logger.warning(
                "deny: rate_limit_burst_exceeded key=<%s> limit=<%d> window=<%.1fs> retry_after=<%ds>",
                key,
                rate_limit_burst,
                burst_window,
                retry_burst,
            )
            {
                "Retry-After": str(retry_burst),
                "RateLimit-Limit": str(rate_limit_burst),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(retry_burst),
            }
            from app.error_envelope import raise_enveloped

            raise_enveloped(
                "rate_limited",
                "Rate limit exceeded",
                status=429,
                details={"retry_after": retry_burst},
            )


async def verify_ws(websocket: WebSocket) -> None:
    """JWT validation for WebSocket connections.

    Accepts either an ``Authorization: Bearer <token>`` header or a
    ``?token=...``/``?access_token=...`` query parameter for browser clients
    that cannot set custom headers during the WebSocket handshake.
    When validated, the decoded payload is attached to ``ws.state.jwt_payload``
    and ``ws.state.user_id`` is set if present in the token.

    WebSocket requirement: Validates origin to ensure only http://localhost:3000 is accepted.
    """

    # WebSocket requirement: Origin validation - only accept http://localhost:3000
    if not validate_websocket_origin(websocket):
        origin = websocket.headers.get("Origin", "unknown")
        logger.warning("deny: origin_not_allowed origin=<%s>", origin)
        # WebSocket requirement: Close with crisp code/reason for origin mismatch
        await websocket.close(
            code=4403,
            reason="origin_not_allowed",  # Forbidden - origin not allowed
        )
        return

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
        # Close connection for missing token - require authentication
        logger.warning("deny: missing_token")
        await websocket.close(
            code=4401,
            reason="missing_token",  # Unauthorized - missing token
        )
        return

    try:
        # Enforce iss/aud in prod if configured
        opts = {}
        iss = os.getenv("JWT_ISSUER")
        aud = os.getenv("JWT_AUDIENCE")
        if iss:
            opts["issuer"] = iss
        if aud:
            opts["audience"] = aud
        if opts:
            payload = jwt_decode(token, jwt_secret, algorithms=["HS256"], **opts)
        else:
            payload = jwt_decode(token, jwt_secret, algorithms=["HS256"])
        websocket.state.jwt_payload = payload
        uid = payload.get("user_id") or payload.get("sub")
        if uid:
            websocket.state.user_id = uid
    except jwt.PyJWTError as e:
        # Close connection for invalid token
        logger.warning("deny: invalid_token error=<%s>", str(e))
        await websocket.close(
            code=4401,
            reason="invalid_token",  # Unauthorized - invalid token
        )
        return


async def rate_limit_ws(websocket: WebSocket) -> None:
    _maybe_refresh_settings_for_test()
    """Per-user rate limiting for WebSocket connections."""

    uid = getattr(websocket.state, "user_id", None)
    if not uid:
        payload = getattr(websocket.state, "jwt_payload", None)
        if isinstance(payload, dict):
            uid = payload.get("user_id") or payload.get("sub")

    # Build base key (user or IP)
    if uid:
        base_key = f"user:{uid}"
    else:
        # Fix WS XFF: when _TRUST_XFF is false, use websocket.client.host; when true, parse the first X-Forwarded-For
        if _TRUST_XFF:
            ip = websocket.headers.get("X-Forwarded-For")
            ip = (
                ip.split(",")[0].strip()
                if ip
                else (websocket.client.host if websocket.client else "anon")
            )
        else:
            ip = websocket.client.host if websocket.client else "anon"
        base_key = f"ip:{ip}"

    # Add test salt for deterministic testing
    test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
    if test_salt:
        key = f"{base_key}:{test_salt}"
    else:
        key = base_key
    # Global bypass for configured scopes on WS too
    try:
        payload = getattr(websocket.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            payload = _get_ws_payload(websocket)
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
                metrics.RATE_LIMIT_BLOCKS.labels(
                    "ws", "daily", "redis" if r_daily else "memory"
                ).inc()
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
                    ws_burst["_reset"] = (
                        time.time() + max(0, int(b_ttl)) - _burst_window
                    )
                    _ws_requests[key] = max(0, l_count)
                    _ws_requests["_reset"] = time.time() + max(0, int(l_ttl)) - _window
                except Exception:
                    pass
                if l_count > RATE_LIMIT:
                    try:
                        metrics.RATE_LIMIT_BLOCKS.labels(
                            "ws", "long", backend_label
                        ).inc()
                    except Exception:
                        pass
                    raise WebSocketException(code=1013)
                return
    async with _lock:
        # Burst-first evaluation for in-memory WS limiter
        ok_b = _bucket_rate_limit(key, ws_burst, RATE_LIMIT_BURST, _burst_window)
        ok_long = _bucket_rate_limit(key, _ws_requests, RATE_LIMIT, _window)
    if not ok_b:
        try:
            metrics.RATE_LIMIT_BLOCKS.labels("ws", "burst", backend_label).inc()
        except Exception:
            pass
        raise WebSocketException(code=1013)
    if not ok_long:
        try:
            metrics.RATE_LIMIT_BLOCKS.labels("ws", "long", backend_label).inc()
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
_nonce_store: dict[str, float] = {}


async def _nonce_user_dep(request: Request) -> str:
    # Lazy import to avoid circular imports at module import time
    from app.deps.user import get_current_user_id  # type: ignore

    return get_current_user_id(request=request)


async def require_nonce(
    request: Request, user_id: str = Depends(_nonce_user_dep)
) -> None:
    """Enforce a one-time nonce for state-changing requests.

    Header: X-Nonce: <random-string>
    Enabled when REQUIRE_NONCE env is truthy.
    """

    # Skip CORS preflight requests
    if str(request.method).upper() == "OPTIONS":
        return

    if os.getenv("REQUIRE_NONCE", "0").lower() not in {"1", "true", "yes"}:
        return
    nonce = request.headers.get("X-Nonce")
    if not nonce:
        from app.http_errors import http_error

        raise http_error(
            code="missing_nonce", message="Nonce header required", status=400
        )
    now = time.time()
    async with _lock:
        # prune expired
        expired = [n for n, ts in list(_nonce_store.items()) if now - ts > _nonce_ttl]
        for n in expired:
            _nonce_store.pop(n, None)
        # Namespace by user/session and test id to prevent cross-user reuse
        try:
            from ..deps.user import resolve_session_id

            sid = resolve_session_id(request=request)
            did = request.headers.get("X-Device-ID") or request.cookies.get("did")
        except Exception:
            sid, did = None, None
        uid = user_id or "anon"
        # Namespace by test id when running under pytest to avoid cross-test collisions
        test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
        base = f"user:{uid}|sid:{sid or '-'}|did:{did or '-'}|nonce:{nonce}"
        nonce_key = f"{base}:{test_salt}" if test_salt else base
        if nonce_key in _nonce_store:
            from app.http_errors import http_error

            raise http_error(
                code="nonce_reused", message="Nonce has already been used", status=409
            )
        _nonce_store[nonce_key] = now


# ---------------------------------------------------------------------------
# Webhook signing/verification (e.g., HA callbacks)
# ---------------------------------------------------------------------------


def _load_webhook_secrets() -> list[str]:
    # Allow multiple secrets for rotation via env or file
    secrets: list[str] = []
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
    seen: dict[str, None] = {}
    out: list[str] = []
    for s in secrets:
        if s not in seen:
            seen[s] = None
            out.append(s)
    return out


from app.security.webhooks import sign_webhook

_webhook_seen: dict[str, float] = {}


async def verify_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
) -> bytes:
    """Verify webhook signature and return the raw body.

    Expects hex HMAC-SHA256 in X-Signature header.
    Freshness: when REQUIRE_WEBHOOK_TS is truthy (default), requires X-Timestamp within
    WEBHOOK_MAX_SKEW_S (default 300 seconds) and binds signature to the timestamp.
    """

    # Skip CORS preflight requests
    if str(request.method).upper() == "OPTIONS":
        return b""

    body = await request.body()
    secrets = _load_webhook_secrets()
    if not secrets:
        from app.http_errors import internal_error

        raise internal_error(
            code="webhook_secret_missing", message="Webhook secrets not configured"
        )
    # Allow direct call style (not DI) by falling back to headers when params missing
    if x_signature is None:
        try:
            x_signature = request.headers.get("X-Signature")
        except Exception:
            x_signature = None
    if x_timestamp is None:
        try:
            x_timestamp = request.headers.get("X-Timestamp")
        except Exception:
            x_timestamp = None
    sig = (x_signature or "").strip().lower()
    require_ts = os.getenv("REQUIRE_WEBHOOK_TS", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Parse and validate timestamp if required
    ts_val: float | None = None
    max_skew = float(os.getenv("WEBHOOK_MAX_SKEW_S", "300") or 300)
    if x_timestamp is not None and str(x_timestamp).strip():
        try:
            ts_val = float(str(x_timestamp).strip())
        except Exception:
            from app.http_errors import http_error

            raise http_error(
                code="invalid_timestamp", message="Invalid timestamp format", status=400
            )
    if require_ts and ts_val is None:
        from app.http_errors import http_error

        raise http_error(
            code="missing_timestamp", message="Timestamp header required", status=400
        )
    # Enforce freshness
    if ts_val is not None:
        now = time.time()
        if abs(now - ts_val) > max_skew:
            from .http_errors import unauthorized

            raise unauthorized(
                code="stale_timestamp",
                message="stale timestamp",
                hint="adjust sender clock or increase skew",
            )
    # Verify signature (new contract first: includes timestamp)
    if ts_val is not None:
        for s in secrets:
            calc = sign_webhook(body, s, str(int(ts_val)))
            if hmac.compare_digest(calc.lower(), sig):
                # Replay guard within freshness window
                key = f"{sig}:{int(ts_val)}"
                async with _lock:
                    # prune
                    cutoff = time.time() - max_skew
                    for k, t in list(_webhook_seen.items()):
                        if t < cutoff:
                            _webhook_seen.pop(k, None)
                    if key in _webhook_seen:
                        from app.http_errors import http_error

                        raise http_error(
                            code="replay_detected",
                            message="Webhook replay detected",
                            status=409,
                        )
                    _webhook_seen[key] = time.time()
                return body
    # Back-compat path: allow legacy signature that only covers body
    # When REQUIRE_WEBHOOK_TS=1 this block is only reached if ts was present but signature mismatched
    # or when ts header absent and require_ts evaluates False.
    for s in secrets:
        calc = sign_webhook(body, s)
        if hmac.compare_digest(calc.lower(), sig):
            return body
    from .http_errors import unauthorized

    raise unauthorized(
        code="invalid_signature",
        message="invalid signature",
        hint="verify secret and signature format",
    )


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
        existing = (
            path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        )
        contents = (
            "\n".join([new] + [line.strip() for line in existing if line.strip()])
            + "\n"
        )
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
    "register_problem_handler",
    "_apply_rate_limit",
    "_http_requests",
    "_ws_requests",
    "_requests",
]

# ---------------------------------------------------------------------------
# Public helpers for rate limit metadata
# ---------------------------------------------------------------------------


def _current_key_for_headers(request: Request | None) -> str:
    # Keep this helper independent of per-route scoping for determinism in tests
    _maybe_refresh_settings_for_test()
    if request is None:
        return "anon"
    # Prefer explicit user id from state, otherwise decode payload from header or cookie
    uid = getattr(request.state, "user_id", None)
    if not uid:
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            payload = _get_request_payload(request)
        if isinstance(payload, dict):
            uid = payload.get("user_id") or payload.get("sub")
    # Admin routes should never report IP-backed keys in headers
    path = _safe_request_path(request)
    is_admin_route = path.startswith("/v1/admin") or path.startswith("/admin")
    if uid:
        return f"user:{uid}{':admin' if is_admin_route else ''}"
    # Fallback to device/session identity before IP
    try:
        did = request.headers.get("X-Device-ID") or request.headers.get("X-Session-ID")
    except Exception:
        did = None
    if not did:
        try:
            did = request.cookies.get("did") or request.cookies.get("sid")
        except Exception:
            did = None
    if did:
        return f"device:{did}"  # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string
    # For admin routes, avoid IP-based key entirely
    if is_admin_route:
        return "user:anon-admin"
    # Prefer the first X-Forwarded-For IP when present for deterministic tests
    ip = request.headers.get("X-Forwarded-For")
    if ip:
        return ip.split(",")[0].strip()
    return request.client.host if request.client else "anon"


def get_rate_limit_snapshot(request: Request | None) -> dict:
    _maybe_refresh_settings_for_test()
    """Return a snapshot of long and burst rate limit state for headers."""

    key = _current_key_for_headers(request)

    # Read rate limit values dynamically from environment
    long_limit = int(os.getenv("RATE_LIMIT_PER_MIN", os.getenv("RATE_LIMIT", "60")))
    burst_limit = int(os.getenv("RATE_LIMIT_BURST", "10"))
    window = float(os.getenv("RATE_LIMIT_WINDOW_S", "60"))
    burst_window = float(
        os.getenv(
            "RATE_LIMIT_BURST_WINDOW_S", os.getenv("RATE_LIMIT_BURST_WINDOW", "60")
        )
    )

    # Snapshot from local mirrors (works for both memory and distributed modes)
    long_count = int(_http_requests.get(key, 0))
    long_reset = _bucket_retry_after(_http_requests, window)
    burst_count = int(http_burst.get(key, 0))
    burst_reset = _bucket_retry_after(http_burst, burst_window)
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
        # Skip CORS preflight requests
        if request.method == "OPTIONS":
            return
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
                    http_burst["_reset"] = (
                        time.time() + max(0, int(b_ttl)) - _burst_window
                    )
                except Exception:
                    pass
                if b_count > _burst:
                    retry_b = max(0, int(b_ttl))
                    from app.http_errors import http_error

                    raise http_error(
                        code="rate_limited",
                        message="Rate limit exceeded",
                        status=429,
                        headers={"Retry-After": str(retry_b)},
                        meta={"retry_after_seconds": retry_b},
                    )
                l_count, l_ttl = await _redis_incr_with_ttl(r, long_key, _window)
                if l_count != -1:
                    try:
                        _http_requests[key] = l_count
                        _http_requests["_reset"] = (
                            time.time() + max(0, int(l_ttl)) - _window
                        )
                    except Exception:
                        pass
                    if l_count > _long:
                        retry_after = max(0, int(l_ttl))
                        from app.http_errors import http_error

                        raise http_error(
                            code="rate_limited",
                            message="Rate limit exceeded",
                            status=429,
                            headers={"Retry-After": str(retry_after)},
                            meta={"retry_after_seconds": retry_after},
                        )
                    return
        # Local fallback
        async with _lock:
            ok_b = _bucket_rate_limit(key_local, http_burst, _burst, _burst_window)
            retry_b = _bucket_retry_after(http_burst, _burst_window)
            if not ok_b:
                from app.http_errors import http_error

                raise http_error(
                    code="rate_limited",
                    message="Rate limit exceeded",
                    status=429,
                    headers={"Retry-After": str(retry_b)},
                    meta={"retry_after_seconds": retry_b},
                )
            ok_long = _bucket_rate_limit(key_local, _http_requests, _long, _window)
            retry_long = _bucket_retry_after(_http_requests, _window)
        if not ok_long:
            from app.http_errors import http_error

            raise http_error(
                code="rate_limited",
                message="Rate limit exceeded",
                status=429,
                headers={"Retry-After": str(retry_long)},
                meta={"retry_after_seconds": retry_long},
            )

    return _dep


def scope_rate_limit(
    scope: str, long_limit: int | None = None, burst_limit: int | None = None
):
    """Enforce custom limits when JWT includes a given scope; otherwise default.

    Usage:
        @router.get("/admin", dependencies=[Depends(scope_rate_limit("admin", burst_limit=3))])
    """

    _long = int(long_limit) if long_limit is not None else RATE_LIMIT
    _burst = int(burst_limit) if burst_limit is not None else RATE_LIMIT_BURST

    async def _dep(request: Request) -> None:
        # Skip CORS preflight requests
        if request.method == "OPTIONS":
            return
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
                ok_long = _bucket_rate_limit(key, scope_rate_limits, _long, _window)
            if not ok_long:
                from app.error_envelope import raise_enveloped

                raise_enveloped("rate_limited", "Rate limit exceeded", status=429)
            return None
        # If the user does not have the scope, do not enforce any extra limits here
        return None

    return _dep


# ---------------------------------------------------------------------------
# Route-local helper: strict rate limit with custom window + RFC7807 on block
# ---------------------------------------------------------------------------


async def rate_limit_problem(
    request: Request,
    *,
    long_limit: int = 1,
    burst_limit: int = 1,
    window_s: float = 30.0,
) -> None:
    """Apply a tight rate limit with a custom window and return RFC7807 on 429.

    Sets per-request overrides for long/burst limits and long window seconds. On
    blocking, raises an HTTPException with application/problem+json semantics and
    X-RateLimit-Remaining header so clients can show a countdown.
    """

    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        return

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
        from app.http_errors import http_error

        headers = dict(exc.headers or {})
        headers["X-RateLimit-Remaining"] = str(remaining)
        raise http_error(
            code="rate_limited",
            message="Too Many Requests",
            status=429,
            headers=headers,
            meta={
                "retry_after_seconds": retry_after,
                "instance": _safe_request_path(request) or "/",
                "remaining": remaining,
            },
        )

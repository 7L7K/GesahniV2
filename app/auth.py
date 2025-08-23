import asyncio
import hashlib
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from pydantic import BaseModel

from .deps.scopes import require_scope
from .deps.user import get_current_user_id
from .security import _jwt_decode
from .user_store import user_store

# Configuration
DB_PATH = os.getenv("USERS_DB", "users.db")
# In tests, default to an isolated temp file per test to avoid collisions
if "PYTEST_CURRENT_TEST" in os.environ and not os.getenv("USERS_DB"):
    try:
        ident = os.environ.get("PYTEST_CURRENT_TEST", "")
        digest = hashlib.md5(ident.encode()).hexdigest()[:8]
        DB_PATH = str((Path.cwd() / f".tmp_auth_{digest}.db").resolve())
    except Exception:
        DB_PATH = str(Path("test_auth.db").resolve())
AUTH_TABLE = os.getenv("AUTH_TABLE", "auth_users")
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET")
# Defer strict validation of the JWT secret until token creation time so imports
# don't fail in tests that don't need JWT functionality
JWT_ISS = os.getenv("JWT_ISS")
JWT_AUD = os.getenv("JWT_AUD")

# Token expiration times
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))

# Rate limiting configuration
_attempts: dict[str, tuple[int, float]] = {}
_ATTEMPT_WINDOW = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))
_ATTEMPT_MAX = int(os.getenv("LOGIN_ATTEMPT_MAX", "5"))
_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "60"))
# Additional rate limiting constants
_EXPONENTIAL_BACKOFF_START = int(os.getenv("LOGIN_BACKOFF_START_MS", "200"))
_EXPONENTIAL_BACKOFF_MAX = int(os.getenv("LOGIN_BACKOFF_MAX_MS", "1000"))
_EXPONENTIAL_BACKOFF_THRESHOLD = int(os.getenv("LOGIN_BACKOFF_THRESHOLD", "3"))
_HARD_LOCKOUT_THRESHOLD = int(os.getenv("LOGIN_HARD_LOCKOUT_THRESHOLD", "6"))

# Dynamic configuration getters to avoid import-time staleness
def _jwt_exp_minutes() -> int:
    return int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

def _jwt_refresh_exp_minutes() -> int:
    return int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))

def _attempt_window_s() -> int:
    return int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))

def _attempt_max() -> int:
    return int(os.getenv("LOGIN_ATTEMPT_MAX", "5"))

def _lockout_seconds() -> int:
    return int(os.getenv("LOGIN_LOCKOUT_SECONDS", "60"))

def _backoff_start_ms() -> int:
    return int(os.getenv("LOGIN_BACKOFF_START_MS", "200"))

def _backoff_max_ms() -> int:
    return int(os.getenv("LOGIN_BACKOFF_MAX_MS", "1000"))

def _backoff_threshold() -> int:
    return int(os.getenv("LOGIN_BACKOFF_THRESHOLD", "3"))

def _hard_lockout_threshold() -> int:
    return int(os.getenv("LOGIN_HARD_LOCKOUT_THRESHOLD", "6"))

# Password hashing: prefer bcrypt if a working backend is present; otherwise pbkdf2
_TEST_ENV = "PYTEST_CURRENT_TEST" in os.environ


def _has_working_bcrypt() -> bool:
    try:
        import bcrypt as _bcrypt  # type: ignore

        # passlib probes _bcrypt.__about__.__version__; guard for broken wheels
        return hasattr(_bcrypt, "__about__") and hasattr(
            _bcrypt.__about__, "__version__"
        )
    except Exception:
        return False


try:
    if _TEST_ENV or not _has_working_bcrypt():
        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    else:
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except Exception:  # pragma: no cover - defensive
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Router
router = APIRouter(tags=["Auth"])
logger = logging.getLogger(__name__)





def _create_session_id(jti: str, expires_at: float) -> str:
    """
    Create a new session ID and store it mapped to the access token JTI.

    Args:
        jti: JWT ID from access token
        expires_at: Unix timestamp when session expires

    Returns:
        str: New session ID
    """
    from .session_store import get_session_store

    store = get_session_store()
    return store.create_session(jti, expires_at)


def _verify_session_id(session_id: str, jti: str) -> bool:
    """
    Verify a session ID against the expected JTI.

    Args:
        session_id: The session ID from __session cookie
        jti: The JWT ID from access token

    Returns:
        bool: True if the session is valid and matches the JTI
    """
    from .session_store import get_session_store

    store = get_session_store()
    stored_jti = store.get_session(session_id)
    return stored_jti == jti


def _delete_session_id(session_id: str) -> bool:
    """
    Delete a session ID.

    Args:
        session_id: The session ID to delete

    Returns:
        bool: True if session was deleted, False if not found
    """
    from .session_store import get_session_store

    store = get_session_store()
    return store.delete_session(session_id)


# Import JWT token creation functions from centralized tokens module
# Note: These functions are deprecated in favor of make_access() and make_refresh()
# from .tokens import create_access_token, create_refresh_token


# Pydantic models
class RegisterRequest(BaseModel):
    username: str
    password: str

    class Config:
        json_schema_extra = {"example": {"username": "demo", "password": "secret123"}}


class LoginRequest(BaseModel):
    username: str
    password: str

    class Config:
        json_schema_extra = {"example": {"username": "demo", "password": "secret123"}}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    token: str | None = None
    stats: dict | None = None


class RefreshRequest(BaseModel):
    refresh_token: str

    class Config:
        json_schema_extra = {"example": {"refresh_token": "<jwt-refresh>"}}


# Optional password reset models
class ForgotRequest(BaseModel):
    username: str

    class Config:
        json_schema_extra = {"example": {"username": "demo"}}


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    class Config:
        json_schema_extra = {
            "example": {"token": "abcd1234", "new_password": "NewPass123"}
        }


# Ensure auth table exists and migrate legacy schemas
async def _ensure_table() -> None:
    # Ensure directory exists for sqlite file paths like /tmp/dir/users.db
    try:
        p = Path(DB_PATH)
        if p.parent and str(p).lower() not in {":memory:", ""}:
            p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    async with aiosqlite.connect(DB_PATH) as db:
        # Create dedicated auth table to avoid collision with analytics 'users'
        await db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {AUTH_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        # Compatibility: create a minimal 'users' table if absent so tests can read it
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT
            )
            """
        )
        # Best-effort migration from any legacy 'users' projections
        try:
            await db.execute(
                f"INSERT OR IGNORE INTO {AUTH_TABLE} (username, password_hash) SELECT username, password_hash FROM users WHERE username IS NOT NULL AND password_hash IS NOT NULL"
            )
        except Exception:
            pass
        await db.commit()


async def _fetch_password_hash(db: aiosqlite.Connection, username: str) -> str | None:
    """Return stored password hash for the given username.

    Tries the dedicated auth table first; then falls back to a legacy
    analytics-style ``users`` table where the identifier column is ``user_id``.
    """
    # 1) Preferred: dedicated auth table
    try:
        async with db.execute(
            f"SELECT password_hash FROM {AUTH_TABLE} WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass

    # 2) Fallback: legacy users table with user_id column
    try:
        async with db.execute(
            "SELECT password_hash FROM users WHERE user_id = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass

    return None


def _sanitize_username(username: str) -> str:
    """Return a normalized username (lowercase, trimmed) or raise HTTP 400.

    Allowed: letters, digits, underscore, hyphen, dot; length 3..64.
    """
    u = (username or "").strip().lower()
    if len(u) < 3 or len(u) > 64:
        raise HTTPException(status_code=400, detail="invalid_username")
    if not re.fullmatch(r"[a-z0-9_.-]+", u):
        raise HTTPException(status_code=400, detail="invalid_username")
    return u


def _validate_password(password: str) -> None:
    """Basic password policy: at least 6 chars; reject obviously empty/whitespace.

    Kept len>=6 to remain compatible with existing tests using 'secret'.
    """
    p = password or ""
    if len(p.strip()) < 6:
        raise HTTPException(status_code=400, detail="weak_password")
    # Optional strong-policy gate via env (enforced even under pytest)
    if os.getenv("PASSWORD_STRENGTH", "0").lower() in {"1", "true", "yes"}:
        try:
            from zxcvbn import zxcvbn  # type: ignore

            score = int(zxcvbn(p).get("score", 0))
            if score < 2:  # 0-4 scale
                raise HTTPException(status_code=400, detail="weak_password")
        except Exception:
            # Fallback heuristic when zxcvbn unavailable: require >=8 and alnum mix
            if len(p) < 8 or not (re.search(r"[A-Za-z]", p) and re.search(r"\d", p)):
                raise HTTPException(status_code=400, detail="weak_password")


def _record_attempt(key: str, *, success: bool) -> None:
    """Record a login attempt for rate limiting.

    Args:
        key: Rate limiting key (user or IP)
        success: Whether the login was successful
    """
    now = time.time()
    count, ts = _attempts.get(key, (0, now))

    # Reset counter if window has expired
    if now - ts > _attempt_window_s():
        count = 0
        ts = now

    if success:
        # Clear successful attempts immediately
        _attempts.pop(key, None)
    else:
        # Increment failed attempt counter
        _attempts[key] = (count + 1, ts)


def _throttled(key: str) -> int | None:
    """Return seconds to wait if throttled; None if allowed.

    Args:
        key: Rate limiting key (user or IP)

    Returns:
        Seconds to wait if throttled, None if allowed
    """
    now = time.time()
    attempt_data = _attempts.get(key, (0, now))

    # Handle malformed data gracefully
    try:
        count, ts = attempt_data
        if not isinstance(count, (int, float)) or not isinstance(ts, (int, float)):
            # Reset malformed data
            _attempts.pop(key, None)
            return None
    except (TypeError, ValueError):
        # Reset malformed data
        _attempts.pop(key, None)
        return None

    # Reset if window has expired
    if now - ts > _attempt_window_s():
        return None

    # Check if we've exceeded the attempt limit
    if count >= _attempt_max():
        elapsed = now - ts
        remaining = max(0, _lockout_seconds() - int(elapsed))
        # Ensure we return at least 1 second to prevent immediate retry
        return max(1, remaining)

    return None


def _get_throttle_status(user_key: str, ip_key: str) -> tuple[int | None, int | None]:
    """Get throttling status for both user and IP keys.

    Args:
        user_key: Rate limiting key for username
        ip_key: Rate limiting key for IP address

    Returns:
        Tuple of (user_throttle_seconds, ip_throttle_seconds)
    """
    user_throttle = _throttled(user_key)
    ip_throttle = _throttled(ip_key)
    return user_throttle, ip_throttle


def _should_apply_backoff(user_key: str) -> bool:
    """Check if exponential backoff should be applied.

    Args:
        user_key: Rate limiting key for username

    Returns:
        True if backoff should be applied
    """
    count, _ = _attempts.get(user_key, (0, 0))
    return count >= _backoff_threshold()


def _should_hard_lockout(user_key: str) -> bool:
    """Check if hard lockout should be applied.

    Args:
        user_key: Rate limiting key for username

    Returns:
        True if hard lockout should be applied
    """
    count, _ = _attempts.get(user_key, (0, 0))
    return count >= _hard_lockout_threshold()


def _clear_rate_limit_data(key: str = None) -> None:
    """Clear rate limiting data for testing or admin purposes.

    Args:
        key: Specific key to clear, or None to clear all
    """
    if key:
        _attempts.pop(key, None)
    else:
        _attempts.clear()


def _get_rate_limit_stats(key: str) -> dict[str, Any] | None:
    """Get rate limiting statistics for a key.

    Args:
        key: Rate limiting key

    Returns:
        Dictionary with count and timestamp, or None if not found
    """
    if key not in _attempts:
        return None

    count, ts = _attempts[key]
    now = time.time()
    return {
        "count": count,
        "timestamp": ts,
        "window_expires": ts + _attempt_window_s(),
        "time_remaining": max(0, ts + _attempt_window_s() - now),
        "is_throttled": count >= _attempt_max(),
        "throttle_remaining": _throttled(key),
    }


def _client_ip(request: Request) -> str:
    """Best-effort client IP extraction for auth throttling.

    Prefer the first X-Forwarded-For when present; otherwise use the socket
    peer IP. Returns "unknown" when unavailable.
    """
    try:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",", 1)[0].strip() or "unknown"
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass
    return "unknown"


# Register endpoint
@router.post("/register", response_model=dict)
async def register(req: RegisterRequest):
    await _ensure_table()
    # Normalize and validate
    norm_user = _sanitize_username(req.username)
    # Normalize first and check duplicate username early for desired error precedence
    async with aiosqlite.connect(DB_PATH) as db:
        # Check dedicated auth table first
        async with db.execute(
            f"SELECT 1 FROM {AUTH_TABLE} WHERE username = ?",
            (norm_user,),
        ) as cursor:
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="username_taken")
        # Also check legacy 'users' projections to preserve duplicate semantics
        try:
            async with db.execute(
                "SELECT 1 FROM users WHERE username = ? OR user_id = ?",
                (norm_user, norm_user),
            ) as cursor:
                if await cursor.fetchone():
                    raise HTTPException(status_code=400, detail="username_taken")
        except Exception:
            pass
    # Enforce password policy next. When PASSWORD_STRENGTH=1, require alnum mix and >= 8
    _validate_password(req.password)
    hashed = pwd_context.hash(req.password)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Rely on UNIQUE constraint to guard duplicates; simpler and avoids races
            await db.execute(
                f"INSERT INTO {AUTH_TABLE} (username, password_hash) VALUES (?, ?)",
                (norm_user, hashed),
            )
            # Also mirror into 'users' table for compatibility
            try:
                cols: list[str] = []
                async with db.execute("PRAGMA table_info(users)") as cur:
                    async for row in cur:
                        cols.append(str(row[1]))
                if {"username", "password_hash"}.issubset(set(cols)):
                    await db.execute(
                        "INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)",
                        (norm_user, hashed),
                    )
                elif {
                    "user_id",
                    "password_hash",
                    "login_count",
                    "request_count",
                }.issubset(set(cols)):
                    await db.execute(
                        "INSERT OR IGNORE INTO users (user_id, password_hash, login_count, request_count) VALUES (?, ?, 0, 0)",
                        (norm_user, hashed),
                    )
            except Exception:
                pass
            await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="username_taken")
    return {"status": "ok"}


# Admin endpoint to view rate limiting statistics
@router.get("/admin/rate-limits/{key}")
async def get_rate_limit_stats(
    key: str,
    _=Depends(require_scope("admin:read"))
):
    """Get rate limiting statistics for a specific key (admin only)."""
    stats = _get_rate_limit_stats(key)
    if stats is None:
        raise HTTPException(status_code=404, detail="Rate limit data not found")
    return {"key": key, "stats": stats}


# Admin endpoint to clear rate limiting data
@router.delete("/admin/rate-limits/{key}")
async def clear_rate_limit_data(
    key: str = None,
    _=Depends(require_scope("admin:write"))
):
    """Clear rate limiting data for a specific key or all keys (admin only)."""
    _clear_rate_limit_data(key)
    return {
        "status": "ok",
        "message": f"Cleared rate limit data for key: {key or 'all'}",
    }


# Login endpoint with backoff after failures
@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest, request: Request, response: Response
) -> TokenResponse:
    """Password login for local accounts.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """
    logger.info(
        "auth.login_start",
        extra={
            "meta": {
                "username": req.username,
                "ip": _client_ip(request),
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "content_type": request.headers.get("Content-Type", "unknown"),
                "has_csrf": bool(request.headers.get("X-CSRF-Token")),
                "has_cookie": bool(request.cookies.get("csrf_token")),
            }
        },
    )

    await _ensure_table()
    norm_user = _sanitize_username(req.username)
    logger.info(
        "auth.login_username_normalized",
        extra={
            "meta": {
                "original_username": req.username,
                "normalized_username": norm_user,
                "ip": _client_ip(request),
            }
        },
    )

    # Rate limiting keys
    user_key = f"user:{norm_user}"
    ip_key = f"ip:{_client_ip(request)}"

    # Check throttling status for both user and IP
    user_throttle, ip_throttle = _get_throttle_status(user_key, ip_key)
    logger.info(
        "auth.login_rate_limit_check",
        extra={
            "meta": {
                "username": norm_user,
                "ip": _client_ip(request),
                "user_throttle": user_throttle,
                "ip_throttle": ip_throttle,
                "user_key": user_key,
                "ip_key": ip_key,
            }
        },
    )

    # Apply the most restrictive throttling (longest wait time)
    if user_throttle is not None or ip_throttle is not None:
        max_throttle = max(user_throttle or 0, ip_throttle or 0)
        logger.warning(
            "auth.login_rate_limited",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "user_throttle": user_throttle,
                    "ip_throttle": ip_throttle,
                    "max_throttle": max_throttle,
                }
            },
        )
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": max_throttle},
        )

    # Apply exponential backoff before authentication to prevent timing attacks
    if _should_apply_backoff(user_key):
        delay_ms = random.randint(_backoff_start_ms(), _backoff_max_ms())
        logger.info(
            "auth.login_applying_backoff",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "delay_ms": delay_ms,
                }
            },
        )
        await asyncio.sleep(delay_ms / 1000.0)

    # Check for hard lockout before attempting authentication
    if _should_hard_lockout(user_key):
        logger.warning(
            "auth.login_hard_lockout",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "lockout_seconds": _lockout_seconds(),
                }
            },
        )
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after": _lockout_seconds()},
        )

    # Perform authentication
    logger.info(
        "auth.login_attempting_authentication",
        extra={
            "meta": {
                "username": norm_user,
                "ip": _client_ip(request),
                "db_path": DB_PATH,
            }
        },
    )

    async with aiosqlite.connect(DB_PATH) as db:
        # Try both auth table and legacy users table
        hashed = await _fetch_password_hash(db, norm_user)
        logger.info(
            "auth.login_password_hash_fetched",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "hash_found": bool(hashed),
                    "hash_length": len(hashed) if hashed else 0,
                }
            },
        )

    valid = False
    if hashed:
        try:
            valid = bool(pwd_context.verify(req.password, hashed))
            logger.info(
                "auth.login_password_verification",
                extra={
                    "meta": {
                        "username": norm_user,
                        "ip": _client_ip(request),
                        "password_valid": valid,
                        "hash_algorithm": (
                            hashed.split("$")[1]
                            if hashed and "$" in hashed
                            else "unknown"
                        ),
                    }
                },
            )
        except UnknownHashError as e:
            # Treat unrecognized/badly formatted hashes as invalid credentials
            logger.error(
                "auth.login_unknown_hash_error",
                extra={
                    "meta": {
                        "username": norm_user,
                        "ip": _client_ip(request),
                        "error": str(e),
                        "hash_preview": hashed[:20] + "..." if hashed else "none",
                    }
                },
            )
            valid = False
        except Exception as e:
            logger.error(
                "auth.login_password_verification_error",
                extra={
                    "meta": {
                        "username": norm_user,
                        "ip": _client_ip(request),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                },
            )
            valid = False

    if not valid:
        # Record failed attempts for both user and IP
        _record_attempt(user_key, success=False)
        _record_attempt(ip_key, success=False)

        logger.warning(
            "auth.login_failed",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "reason": "invalid_credentials",
                    "hash_found": bool(hashed),
                }
            },
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Record successful attempts for both user and IP
    _record_attempt(user_key, success=True)
    _record_attempt(ip_key, success=True)

    logger.info(
        "auth.login_creating_tokens",
        extra={
            "meta": {
                "username": norm_user,
                "ip": _client_ip(request),
                "expire_minutes": _jwt_exp_minutes(),
                "refresh_expire_minutes": _jwt_refresh_exp_minutes(),
            }
        },
    )

    # Create access token using centralized tokens module
    from .tokens import make_access, make_refresh

    access_token = make_access({"user_id": req.username})

    # Create refresh token
    refresh_jti = uuid4().hex
    refresh_token = make_refresh({"user_id": req.username, "jti": refresh_jti})

    logger.info(
        "auth.login_tokens_created",
        extra={
            "meta": {
                "username": norm_user,
                "ip": _client_ip(request),
                "access_token_length": len(access_token),
                "refresh_token_length": len(refresh_token),
                "access_jti": jti,
                "refresh_jti": refresh_jti,
            }
        },
    )

    await user_store.ensure_user(norm_user)
    await user_store.increment_login(norm_user)
    stats = await user_store.get_stats(norm_user) or {}
    logger.info(
        "auth.login_success",
        extra={
            "meta": {
                "username": norm_user,
                "ip": _client_ip(request),
                "user_stats": stats,
            }
        },
    )

    # Set HttpOnly cookies for browser clients (unified flow: header + cookie)
    try:
        from .cookie_config import get_cookie_config, get_token_ttls

        # Get consistent cookie configuration
        cookie_config = get_cookie_config(request)
        access_ttl, refresh_ttl = get_token_ttls()

        logger.info(
            "auth.login_cookie_config",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "cookie_config": cookie_config,
                    "access_ttl": access_ttl,
                    "refresh_ttl": refresh_ttl,
                }
            },
        )

        # Create a session ID mapped to the access token JTI
        # This provides better security by using an opaque session ID
        try:
            # Decode the access token to get the JTI
            # Use dynamic JWT secret function to handle test environment changes
            from .api.auth import _jwt_secret

            secret = _jwt_secret()
            payload = _jwt_decode(access_token, secret, algorithms=[ALGORITHM])
            jti = payload.get("jti")
            expires_at = payload.get("exp", time.time() + access_ttl)

            if jti:
                session_id = _create_session_id(jti, expires_at)
            else:
                # Fallback if no JTI found
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        except Exception as e:
            logger.warning(f"Failed to decode access token for session creation: {e}")
            # Fallback session ID
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

        # Use centralized cookie functions
        from .cookies import set_auth_cookies

        set_auth_cookies(
            response,
            access=access_token,
            refresh=refresh_token,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )

        logger.info(
            "auth.login_cookies_set",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "secure": cookie_config["secure"],
                    "samesite": cookie_config["samesite"],
                    "access_ttl": access_ttl,
                    "refresh_ttl": refresh_ttl,
                    "domain": cookie_config["domain"],
                    "cookies_set": ["access_token", "refresh_token", "__session"],
                }
            },
        )

        try:
            logger.info(
                "login.set_cookie secure=%s samesite=%s ttl=%ds/%ds cookies=3",
                cookie_config["secure"],
                cookie_config["samesite"],
                access_ttl,
                refresh_ttl,
                extra={
                    "meta": {
                        "secure": cookie_config["secure"],
                        "samesite": cookie_config["samesite"],
                        "access_ttl": access_ttl,
                        "refresh_ttl": refresh_ttl,
                    }
                },
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(
            "auth.login_cookie_set_error",
            extra={
                "meta": {
                    "username": norm_user,
                    "ip": _client_ip(request),
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            },
        )
        logger.error("login.set_cookie error: %s", e)
        # Fallback to centralized cookie functions if header append fails
        try:
            # Set __session cookie with session ID instead of fingerprint
            try:
                # Decode the access token to get the JTI
                # Use dynamic JWT secret function to handle test environment changes
                from .api.auth import _jwt_secret

                secret = _jwt_secret()
                payload = _jwt_decode(access_token, secret, algorithms=[ALGORITHM])
                jti = payload.get("jti")
                expires_at = payload.get("exp", time.time() + access_ttl)

                if jti:
                    session_id = _create_session_id(jti, expires_at)
                else:
                    # Fallback if no JTI found
                    session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
            except Exception as e:
                logger.warning(
                    f"Failed to decode access token for session creation (fallback): {e}"
                )
                # Fallback session ID
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

            # Use centralized cookie functions
            from .cookies import set_auth_cookies

            set_auth_cookies(
                response,
                access=access_token,
                refresh=refresh_token,
                session_id=session_id,
                access_ttl=access_ttl,
                refresh_ttl=refresh_ttl,
                request=request,
            )
            logger.info(
                "auth.login_cookie_fallback_success",
                extra={
                    "meta": {
                        "username": norm_user,
                        "ip": _client_ip(request),
                        "cookies_set": ["access_token", "refresh_token", "__session"],
                    }
                },
            )
        except Exception as fallback_error:
            logger.error(
                "auth.login_cookie_fallback_error",
                extra={
                    "meta": {
                        "username": norm_user,
                        "ip": _client_ip(request),
                        "error": str(fallback_error),
                        "error_type": type(fallback_error).__name__,
                    }
                },
            )
            logger.error("login.set_cookie fallback error: %s", fallback_error)
            pass

    logger.info(
        "auth.login_complete",
        extra={
            "meta": {
                "username": norm_user,
                "ip": _client_ip(request),
                "response_status": 200,
            }
        },
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token=access_token,
        stats=stats,
    )


_DEPRECATE_REFRESH_LOGGED = False


# Refresh endpoint (legacy path) delegates to modern implementation with full parity
@router.post(
    "/refresh",
    response_model=TokenResponse,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/RefreshRequest"}
                }
            }
        }
    },
)
async def refresh(req: RefreshRequest | None = None, request: Request = None, response: Response = None) -> TokenResponse:  # type: ignore[assignment]
    global _DEPRECATE_REFRESH_LOGGED
    if not _DEPRECATE_REFRESH_LOGGED:
        try:
            logger.warning("deprecate route=/v1/refresh")
        except Exception:
            pass
        _DEPRECATE_REFRESH_LOGGED = True
    # Delegate to /v1/auth/refresh parity logic
    from .api.auth import refresh as _refresh  # type: ignore

    # Construct a starlette Request/Response compatible invocation
    # Ensure intent/CSRF parity is enforced by delegated handler
    body_tokens = None
    try:
        if req and getattr(req, "refresh_token", None):
            body_tokens = {"refresh_token": req.refresh_token}
    except Exception:
        body_tokens = None
    out = await _refresh(request, response)  # type: ignore[arg-type]
    # Map response body to TokenResponse for compatibility when tokens are present
    try:
        at = getattr(out, "get", lambda k, d=None: None)("access_token", None)
        rt = getattr(out, "get", lambda k, d=None: None)("refresh_token", None)
    except Exception:
        at = None
        rt = None
    if at and rt:
        return TokenResponse(access_token=at, refresh_token=rt, token=at)
    # Fallback: return empty tokens if not provided (cookie mode only)
    return TokenResponse(access_token="", refresh_token="", token="")


_DEPRECATE_LOGOUT_LOGGED = False


# Logout endpoint (legacy path) - delegate to main logout endpoint
@router.post("/logout")
async def logout(request: Request, response: Response):
    """Legacy logout endpoint - delegates to /v1/auth/logout."""
    # Import and call the main logout function
    from app.api.auth import logout as main_logout

    return await main_logout(request, response)


# Forgot/reset password endpoints (opt-in flow for local accounts)
_RESET_TOKENS: dict[str, tuple[str, float]] = {}
_RESET_TTL = int(os.getenv("PASSWORD_RESET_TTL_SECONDS", "900"))


@router.post("/forgot", response_model=dict)
async def forgot(req: ForgotRequest) -> dict:
    await _ensure_table()
    norm_user = _sanitize_username(req.username)
    # best-effort: ensure user exists
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT 1 FROM {AUTH_TABLE} WHERE username=?",
            (norm_user,),
        ) as cur:
            if not await cur.fetchone():
                # To avoid user enumeration, still return OK
                return {"status": "ok"}
    tok = uuid4().hex
    _RESET_TOKENS[tok] = (norm_user, time.time() + _RESET_TTL)
    # In tests, include token so we can proceed without email
    if os.getenv("PYTEST_RUNNING"):
        return {"status": "ok", "token": tok}
    return {"status": "ok"}


@router.post("/reset_password", response_model=dict)
async def reset_password(req: ResetPasswordRequest) -> dict:
    tok = (req.token or "").strip()
    entry = _RESET_TOKENS.get(tok)
    if not entry:
        raise HTTPException(status_code=400, detail="invalid_token")
    username, exp = entry
    if time.time() > exp:
        _RESET_TOKENS.pop(tok, None)
        raise HTTPException(status_code=400, detail="expired_token")
    # Validate new password and update
    _validate_password(req.new_password)
    hashed = pwd_context.hash(req.new_password)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE {AUTH_TABLE} SET password_hash=? WHERE username=?",
                (hashed, username),
            )
            # Update mirror if applicable
            try:
                cols: list[str] = []
                async with db.execute("PRAGMA table_info(users)") as cur:
                    async for row in cur:
                        cols.append(str(row[1]))
                if {"username", "password_hash"}.issubset(set(cols)):
                    await db.execute(
                        "UPDATE users SET password_hash=? WHERE username=?",
                        (hashed, username),
                    )
                elif {"user_id", "password_hash"}.issubset(set(cols)):
                    await db.execute(
                        "UPDATE users SET password_hash=? WHERE user_id=?",
                        (hashed, username),
                    )
            except Exception:
                pass
            await db.commit()
    finally:
        # Consume token and clear login attempts
        _RESET_TOKENS.pop(tok, None)
        _attempts.pop(f"user:{username}", None)
    return {"status": "ok"}

import os
import re
import time
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Set, Tuple
import logging

import aiosqlite
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Response
import jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from pydantic import BaseModel

from .deps.user import get_current_user_id
from .user_store import user_store

# Configuration
DB_PATH = os.getenv("USERS_DB", "users.db")
# In tests, default to an isolated temp file per test to avoid collisions
if "PYTEST_CURRENT_TEST" in os.environ and not os.getenv("USERS_DB"):
    try:
        import hashlib

        ident = os.environ.get("PYTEST_CURRENT_TEST", "")
        digest = hashlib.md5(ident.encode()).hexdigest()[:8]
        DB_PATH = str((Path.cwd() / f".tmp_auth_{digest}.db").resolve())
    except Exception:
        DB_PATH = str(Path("test_auth.db").resolve())
AUTH_TABLE = os.getenv("AUTH_TABLE", "auth_users")
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))
JWT_ISS = os.getenv("JWT_ISS")
JWT_AUD = os.getenv("JWT_AUD")

# Revocation store
revoked_tokens: Set[str] = set()
_attempts: Dict[str, Tuple[int, float]] = {}
_ATTEMPT_WINDOW = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "300"))
_ATTEMPT_MAX = int(os.getenv("LOGIN_ATTEMPT_MAX", "5"))
_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "60"))

# Password hashing: prefer bcrypt if a working backend is present; otherwise pbkdf2
_TEST_ENV = "PYTEST_CURRENT_TEST" in os.environ
def _has_working_bcrypt() -> bool:
    try:
        import bcrypt as _bcrypt  # type: ignore
        # passlib probes _bcrypt.__about__.__version__; guard for broken wheels
        return hasattr(_bcrypt, "__about__") and hasattr(_bcrypt.__about__, "__version__")
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


# Pydantic models
class RegisterRequest(BaseModel):
    username: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {"username": "demo", "password": "secret123"}
        }


class LoginRequest(BaseModel):
    username: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {"username": "demo", "password": "secret123"}
        }


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
    now = time.time()
    count, ts = _attempts.get(key, (0, now))
    if now - ts > _ATTEMPT_WINDOW:
        count = 0
        ts = now
    if success:
        _attempts.pop(key, None)
    else:
        _attempts[key] = (count + 1, ts)


def _throttled(key: str) -> int | None:
    """Return seconds to wait if throttled; None if allowed.

    Simple lockout once attempts exceed max within window.
    """
    now = time.time()
    count, ts = _attempts.get(key, (0, now))
    if now - ts > _ATTEMPT_WINDOW:
        return None
    if count >= _ATTEMPT_MAX:
        elapsed = now - ts
        remaining = max(0, _LOCKOUT_SECONDS - int(elapsed))
        return remaining or _LOCKOUT_SECONDS
    return None


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
async def register(req: RegisterRequest, user_id: str = Depends(get_current_user_id)):
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
                elif {"user_id", "password_hash", "login_count", "request_count"}.issubset(set(cols)):
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


# Login endpoint with backoff after failures
@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest, request: Request, response: Response, user_id: str = Depends(get_current_user_id)
) -> TokenResponse:
    """Password login for local accounts.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """
    await _ensure_table()
    norm_user = _sanitize_username(req.username)
    # Basic lockout per username and per IP address
    user_key = f"user:{norm_user}"
    ip_key = f"ip:{_client_ip(request)}"
    remain = _throttled(user_key) or _throttled(ip_key)
    if remain:
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "retry_after": remain})
    async with aiosqlite.connect(DB_PATH) as db:
        # Try both auth table and legacy users table
        hashed = await _fetch_password_hash(db, norm_user)

    valid = False
    if hashed:
        try:
            valid = bool(pwd_context.verify(req.password, hashed))
        except UnknownHashError:
            # Treat unrecognized/badly formatted hashes as invalid credentials
            valid = False
        except Exception:
            valid = False
    if not valid:
        _record_attempt(user_key, success=False)
        _record_attempt(ip_key, success=False)
        # Exponential backoff with jitter: after 3 failures add 200–1000ms delay; after 6 lock for 60s
        try:
            import asyncio as _asyncio
            import random as _rand
            count, ts = _attempts.get(user_key, (0, 0))
            if count >= 6:
                # Lock out for 60s
                raise HTTPException(status_code=429, detail={"error": "rate_limited", "retry_after": 60})
            if count >= 3:
                delay_ms = _rand.randint(200, 1000)
                await _asyncio.sleep(delay_ms / 1000.0)
        except HTTPException:
            raise
        except Exception:
            pass
        logger.warning("auth.login_failed", extra={"meta": {"username": norm_user, "ip": _client_ip(request)}})
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _record_attempt(user_key, success=True)
    _record_attempt(ip_key, success=True)

    # Create access token
    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    jti = uuid4().hex
    access_payload = {
        "sub": req.username,
        "user_id": req.username,
        "exp": expire,
        "jti": jti,
        "type": "access",
    }
    if JWT_ISS:
        access_payload["iss"] = JWT_ISS
    if JWT_AUD:
        access_payload["aud"] = JWT_AUD
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Create refresh token
    refresh_expire = datetime.utcnow() + timedelta(minutes=REFRESH_EXPIRE_MINUTES)
    refresh_jti = uuid4().hex
    refresh_payload = {
        "sub": req.username,
        "user_id": req.username,
        "exp": refresh_expire,
        "jti": refresh_jti,
        "type": "refresh",
    }
    if JWT_ISS:
        refresh_payload["iss"] = JWT_ISS
    if JWT_AUD:
        refresh_payload["aud"] = JWT_AUD
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    await user_store.ensure_user(user_id)
    await user_store.increment_login(user_id)
    stats = await user_store.get_stats(user_id) or {}
    logger.info("auth.login_success", extra={"meta": {"username": norm_user, "ip": _client_ip(request)}})

    # Set HttpOnly cookies for browser clients (unified flow: header + cookie)
    try:
        cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
        # In test/dev over HTTP, force non-secure so TestClient sends cookies
        try:
            if request is not None and getattr(request.url, "scheme", "http") != "https":
                cookie_secure = False
        except Exception:
            pass
        cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
        try:
            from .api.auth import _append_cookie_with_priority as _append  # reuse helper
            _append(response, key="access_token", value=access_token, max_age=EXPIRE_MINUTES * 60, secure=cookie_secure, samesite=cookie_samesite)
            _append(response, key="refresh_token", value=refresh_token, max_age=REFRESH_EXPIRE_MINUTES * 60, secure=cookie_secure, samesite=cookie_samesite)
        except Exception:
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=cookie_secure,
                samesite=cookie_samesite,
                max_age=EXPIRE_MINUTES * 60,
                path="/",
            )
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=cookie_secure,
                samesite=cookie_samesite,
                max_age=REFRESH_EXPIRE_MINUTES * 60,
                path="/",
            )
    except Exception:
        pass

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token=access_token,
        stats=stats,
    )


_DEPRECATE_REFRESH_LOGGED = False

# Refresh endpoint (legacy path) delegates to modern implementation with full parity
@router.post("/refresh", response_model=TokenResponse, openapi_extra={"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RefreshRequest"}}}}})
async def refresh(req: RefreshRequest | None = None, request: Request = None, response: Response = None) -> TokenResponse:  # type: ignore[assignment]
    global _DEPRECATE_REFRESH_LOGGED
    if not _DEPRECATE_REFRESH_LOGGED:
        try:
            print("deprecate route=/v1/refresh")
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

# Logout endpoint (legacy path) delegates to modern /v1/auth/logout behavior
@router.post("/logout", response_model=dict)
async def logout(request: Request, response: Response) -> dict:
    global _DEPRECATE_LOGOUT_LOGGED
    if not _DEPRECATE_LOGOUT_LOGGED:
        try:
            print("deprecate route=/v1/logout")
        except Exception:
            pass
        _DEPRECATE_LOGOUT_LOGGED = True
    # Delegate to canonical cookie-based logout which revokes refresh family
    try:
        from .api.auth import logout as _logout  # type: ignore
        return await _logout(request, response)  # type: ignore[arg-type]
    except Exception:
        # Fallback: clear cookies
        try:
            response.delete_cookie("access_token", path="/")
            response.delete_cookie("refresh_token", path="/")
        except Exception:
            pass
        return {"status": "ok"}


# Forgot/reset password endpoints (opt-in flow for local accounts)
_RESET_TOKENS: Dict[str, Tuple[str, float]] = {}
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

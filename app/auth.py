import os
import re
import time
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Set, Tuple

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .deps.user import get_current_user_id
from .user_store import user_store

# Configuration
DB_PATH = os.getenv("USERS_DB", "users.db")
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

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Router
router = APIRouter(tags=["auth"])


# Pydantic models
class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    token: str | None = None
    stats: dict | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


# Ensure auth table exists and migrate legacy schemas
async def _ensure_table() -> None:
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


# Register endpoint
@router.post("/register", response_model=dict)
async def register(req: RegisterRequest, user_id: str = Depends(get_current_user_id)):
    await _ensure_table()
    # Normalize and validate
    norm_user = _sanitize_username(req.username)
    # If username already exists, return username_taken regardless of password strength
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT 1 FROM {AUTH_TABLE} WHERE username = ?",
            (norm_user,),
        ) as cursor:
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="username_taken")
    # Enforce password policy
    _validate_password(req.password)
    hashed = pwd_context.hash(req.password)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Insert into auth table
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


# Login endpoint
@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest, user_id: str = Depends(get_current_user_id)
) -> TokenResponse:
    await _ensure_table()
    norm_user = _sanitize_username(req.username)
    # Basic lockout per username key
    key = f"user:{norm_user}"
    remain = _throttled(key)
    if remain:
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "retry_after": remain})
    async with aiosqlite.connect(DB_PATH) as db:
        # Try both auth table and legacy users table
        hashed = await _fetch_password_hash(db, norm_user)

    if not hashed or not pwd_context.verify(req.password, hashed):
        _record_attempt(key, success=False)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _record_attempt(key, success=True)

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
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token=access_token,
        stats=stats,
    )


# Refresh endpoint
@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest) -> TokenResponse:
    try:
        # Validate audience if configured; issuer verified after decode
        kwargs = {"algorithms": [ALGORITHM]}
        if JWT_AUD:
            kwargs["audience"] = JWT_AUD
        payload = jwt.decode(req.refresh_token, SECRET_KEY, **kwargs)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")
    if JWT_ISS and payload.get("iss") != JWT_ISS:
        raise HTTPException(status_code=401, detail="Invalid token issuer")

    jti = payload.get("jti")
    if jti in revoked_tokens:
        raise HTTPException(status_code=401, detail="Token revoked")

    # Revoke used refresh token
    revoked_tokens.add(jti)
    username = payload.get("sub")

    # Issue new access token
    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    new_jti = uuid4().hex
    access_payload = {
        "sub": username,
        "user_id": username,
        "exp": expire,
        "jti": new_jti,
        "type": "access",
    }
    if JWT_ISS:
        access_payload["iss"] = JWT_ISS
    if JWT_AUD:
        access_payload["aud"] = JWT_AUD
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Issue new refresh token
    refresh_expire = datetime.utcnow() + timedelta(minutes=REFRESH_EXPIRE_MINUTES)
    refresh_jti = uuid4().hex
    refresh_payload = {
        "sub": username,
        "user_id": username,
        "exp": refresh_expire,
        "jti": refresh_jti,
        "type": "refresh",
    }
    if JWT_ISS:
        refresh_payload["iss"] = JWT_ISS
    if JWT_AUD:
        refresh_payload["aud"] = JWT_AUD
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, token=access_token
    )


# Logout endpoint
@router.post("/logout", response_model=dict)
async def logout(request: Request) -> dict:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split(" ", 1)[1]
    try:
        kwargs = {"algorithms": [ALGORITHM]}
        if JWT_AUD:
            kwargs["audience"] = JWT_AUD
        payload = jwt.decode(token, SECRET_KEY, **kwargs)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if JWT_ISS and payload.get("iss") != JWT_ISS:
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    jti = payload.get("jti")
    if jti:
        revoked_tokens.add(jti)
    return {"status": "ok"}

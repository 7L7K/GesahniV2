import os
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Set

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .deps.user import get_current_user_id
from .user_store import user_store

# Configuration
DB_PATH = os.getenv("USERS_DB", "users.db")
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))

# Revocation store
revoked_tokens: Set[str] = set()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Router
router = APIRouter()


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


# Ensure user table exists
async def _ensure_table() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        await db.commit()


# Register endpoint
@router.post("/register", response_model=dict)
async def register(req: RegisterRequest, user_id: str = Depends(get_current_user_id)):
    await _ensure_table()
    hashed = pwd_context.hash(req.password)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (req.username, hashed),
            )
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
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (req.username,),
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not pwd_context.verify(req.password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create access token
    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    jti = uuid4().hex
    access_payload = {
        "sub": req.username,
        "exp": expire,
        "jti": jti,
        "type": "access",
    }
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Create refresh token
    refresh_expire = datetime.utcnow() + timedelta(minutes=REFRESH_EXPIRE_MINUTES)
    refresh_jti = uuid4().hex
    refresh_payload = {
        "sub": req.username,
        "exp": refresh_expire,
        "jti": refresh_jti,
        "type": "refresh",
    }
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
        payload = jwt.decode(req.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Invalid token type")

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
        "exp": expire,
        "jti": new_jti,
        "type": "access",
    }
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Issue new refresh token
    refresh_expire = datetime.utcnow() + timedelta(minutes=REFRESH_EXPIRE_MINUTES)
    refresh_jti = uuid4().hex
    refresh_payload = {
        "sub": username,
        "exp": refresh_expire,
        "jti": refresh_jti,
        "type": "refresh",
    }
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    jti = payload.get("jti")
    if jti:
        revoked_tokens.add(jti)
    return {"status": "ok"}

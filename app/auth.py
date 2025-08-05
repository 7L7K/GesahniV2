import os
from datetime import datetime, timedelta

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .deps.user import get_current_user_id
from .user_store import user_store

# Configuration
DB_PATH = os.getenv("USERS_DB", "users.db")
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

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


# Ensure user table exists
async def _ensure_table() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
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
                "INSERT INTO auth_users (username, password_hash) VALUES (?, ?)",
                (req.username, hashed),
            )
            await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="username_taken")
    return {"status": "ok"}


# Login endpoint
@router.post("/login", response_model=dict)
async def login(req: LoginRequest, user_id: str = Depends(get_current_user_id)) -> dict:
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM auth_users WHERE username = ?",
            (req.username,),
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not pwd_context.verify(req.password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    payload = {"sub": req.username, "exp": expire, "user_id": user_id}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    await user_store.ensure_user(user_id)
    await user_store.increment_login(user_id)
    stats = await user_store.get_stats(user_id)

    return {"token": token, "stats": stats}

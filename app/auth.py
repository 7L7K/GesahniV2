import os
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import aiosqlite
from passlib.context import CryptContext
from jose import jwt

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
type LoginResponse = dict
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

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
async def register(req: RegisterRequest):
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
async def login(req: LoginRequest) -> TokenResponse:
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM users WHERE username = ?", (req.username,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not pwd_context.verify(req.password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expire = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    payload = {"sub": req.username, "exp": expire}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return TokenResponse(access_token=token)

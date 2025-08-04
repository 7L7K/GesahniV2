import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import aiosqlite
from passlib.context import CryptContext

DB_PATH = os.getenv("USERS_DB", "users.db")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    password: str


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


@router.post("/register")
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

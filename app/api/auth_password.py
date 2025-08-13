from __future__ import annotations

import os
from typing import Dict

import aiosqlite
from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext


router = APIRouter(tags=["auth"], include_in_schema=False)


_pwd = CryptContext(schemes=["argon2", "pbkdf2_sha256"], deprecated="auto")
DB = os.getenv("USERS_DB", "users.db")


async def _ensure():
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users(
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL
            )
            """
        )
        await db.commit()


@router.post("/auth/register_pw")
async def register_pw(body: Dict[str, str]):
    await _ensure()
    u = (body.get("username") or "").strip().lower()
    p = body.get("password") or ""
    if not u or len(p) < 6:
        raise HTTPException(status_code=400, detail="invalid")
    h = _pwd.hash(p)
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT INTO auth_users(username,password_hash) VALUES(?,?)", (u, h))
            await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="username_taken")
    return {"status": "ok"}


@router.post("/auth/login_pw")
async def login_pw(body: Dict[str, str]):
    await _ensure()
    u = (body.get("username") or "").strip().lower()
    p = body.get("password") or ""
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT password_hash FROM auth_users WHERE username=?", (u,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="invalid")
    if not _pwd.verify(p, row[0]):
        raise HTTPException(status_code=401, detail="invalid")
    return {"status": "ok"}


__all__ = ["router"]



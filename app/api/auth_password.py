from __future__ import annotations

import os

import aiosqlite
from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext
from app.db.paths import resolve_db_path

router = APIRouter(tags=["auth"], include_in_schema=False)


_pwd = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


def _db_path() -> str:
    """Resolve the users DB path consistently with the rest of the app.

    Uses resolve_db_path so tests that set GESAHNI_TEST_DB_DIR and env-based
    overrides behave identically between register/login code paths.
    """
    return str(resolve_db_path("USERS_DB", "users.db"))


async def _ensure():
    async with aiosqlite.connect(_db_path()) as db:
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
async def register_pw(body: dict[str, str]):
    await _ensure()
    u = (body.get("username") or "").strip().lower()
    p = body.get("password") or ""
    if not u or len(p) < 6:
        raise HTTPException(status_code=400, detail="invalid")
    h = _pwd.hash(p)
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "INSERT INTO auth_users(username,password_hash) VALUES(?,?)", (u, h)
            )
            await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="username_taken")
    return {"status": "ok"}


@router.post("/auth/login_pw")
async def login_pw(body: dict[str, str]):
    await _ensure()
    u = (body.get("username") or "").strip().lower()
    p = body.get("password") or ""
    async with aiosqlite.connect(_db_path()) as db:
        async with db.execute(
            "SELECT password_hash FROM auth_users WHERE username=?", (u,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        from ..http_errors import unauthorized

        raise unauthorized(code="invalid_credentials", message="invalid credentials", hint="check username/password")
    if not _pwd.verify(p, row[0]):
        from ..http_errors import unauthorized

        raise unauthorized(code="invalid_credentials", message="invalid credentials", hint="check username/password")
    return {"status": "ok"}


__all__ = ["router"]

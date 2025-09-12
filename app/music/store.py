from __future__ import annotations

import json
import os
import time

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from app.db.paths import resolve_db_path


def _db_path() -> str:
    return str(resolve_db_path("MUSIC_DB", "music.db"))
MASTER_KEY = os.getenv("MUSIC_MASTER_KEY")


def _fernet() -> Fernet | None:
    if not MASTER_KEY:
        return None
    return Fernet(MASTER_KEY.encode())


async def _ensure_tables(db_path: str | None = None) -> None:
    p = db_path or _db_path()
    async with aiosqlite.connect(p) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_tokens (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                access_token BLOB NOT NULL,
                refresh_token BLOB,
                scope TEXT,
                expires_at INTEGER,
                updated_at INTEGER,
                PRIMARY KEY (user_id, provider)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_devices (
                provider TEXT NOT NULL,
                device_id TEXT NOT NULL,
                room TEXT,
                name TEXT,
                last_seen INTEGER,
                capabilities TEXT,
                PRIMARY KEY (provider, device_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_preferences (
                user_id TEXT PRIMARY KEY,
                default_provider TEXT,
                quiet_start TEXT DEFAULT '22:00',
                quiet_end TEXT DEFAULT '07:00',
                quiet_max_volume INTEGER DEFAULT 30,
                allow_explicit INTEGER DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                room TEXT,
                provider TEXT,
                device_id TEXT,
                started_at INTEGER,
                ended_at INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_queue (
                session_id TEXT,
                position INTEGER,
                provider TEXT,
                entity_type TEXT,
                entity_id TEXT,
                meta JSON,
                PRIMARY KEY (session_id, position)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_feedback (
                user_id TEXT,
                track_id TEXT,
                provider TEXT,
                action TEXT,
                ts INTEGER
            )
            """
        )

        # idempotency table for mutating routes
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_idempotency (
                idempotency_key TEXT PRIMARY KEY,
                user_id TEXT,
                response_json TEXT,
                created_at INTEGER
            )
            """
        )

        await db.commit()


def _encrypt(b: bytes) -> bytes:
    f = _fernet()
    return f.encrypt(b) if f else b


def _decrypt(b: bytes) -> bytes:
    f = _fernet()
    if not f:
        return b
    try:
        return f.decrypt(b)
    except InvalidToken:
        raise


async def upsert_token(user_id: str, provider: str, access_token: bytes, refresh_token: bytes | None = None, scope: str | None = None, expires_at: int | None = None, db_path: str | None = None) -> None:
    p = db_path or _db_path()
    at_enc = _encrypt(access_token)
    rt_enc = _encrypt(refresh_token) if refresh_token else None
    now = int(time.time())
    async with aiosqlite.connect(p) as db:
        await db.execute(
            "INSERT OR REPLACE INTO music_tokens (user_id, provider, access_token, refresh_token, scope, expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, provider, at_enc, rt_enc, scope, expires_at, now),
        )
        await db.commit()


async def get_token(user_id: str, provider: str, db_path: str | None = None) -> dict | None:
    p = db_path or _db_path()
    async with aiosqlite.connect(p) as db:
        cur = await db.execute("SELECT access_token, refresh_token, scope, expires_at, updated_at FROM music_tokens WHERE user_id = ? AND provider = ?", (user_id, provider))
        row = await cur.fetchone()
        if not row:
            return None
        at, rt, scope, expires_at, updated_at = row
        return {
            "access_token": _decrypt(at),
            "refresh_token": _decrypt(rt) if rt else None,
            "scope": scope,
            "expires_at": expires_at,
            "updated_at": updated_at,
        }


async def get_preferences(user_id: str, db_path: str | None = None) -> dict:
    """Return music preferences for a user, falling back to env defaults."""
    p = db_path or _db_path()
    async with aiosqlite.connect(p) as db:
        cur = await db.execute("SELECT default_provider, quiet_start, quiet_end, quiet_max_volume, allow_explicit FROM music_preferences WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return {
                "default_provider": os.getenv("MUSIC_DEFAULT_PROVIDER", "spotify"),
                "quiet_start": os.getenv("MUSIC_QUIET_START", "22:00"),
                "quiet_end": os.getenv("MUSIC_QUIET_END", "07:00"),
                "quiet_max_volume": int(os.getenv("MUSIC_QUIET_MAX_VOLUME", "30")),
                "allow_explicit": int(os.getenv("MUSIC_ALLOW_EXPLICIT", "1")),
            }
        default_provider, quiet_start, quiet_end, quiet_max_volume, allow_explicit = row
        return {
            "default_provider": default_provider or os.getenv("MUSIC_DEFAULT_PROVIDER", "spotify"),
            "quiet_start": quiet_start or os.getenv("MUSIC_QUIET_START", "22:00"),
            "quiet_end": quiet_end or os.getenv("MUSIC_QUIET_END", "07:00"),
            "quiet_max_volume": int(quiet_max_volume) if quiet_max_volume is not None else int(os.getenv("MUSIC_QUIET_MAX_VOLUME", "30")),
            "allow_explicit": int(allow_explicit) if allow_explicit is not None else int(os.getenv("MUSIC_ALLOW_EXPLICIT", "1")),
        }


async def get_idempotent(key: str, user_id: str, db_path: str | None = None) -> dict | None:
    p = db_path or _db_path()
    async with aiosqlite.connect(p) as db:
        cur = await db.execute("SELECT response_json FROM music_idempotency WHERE idempotency_key = ? AND user_id = ?", (key, user_id))
        row = await cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None


async def set_idempotent(key: str, user_id: str, response: dict, db_path: str | None = None) -> None:
    p = db_path or _db_path()
    now = int(time.time())
    async with aiosqlite.connect(p) as db:
        await db.execute("INSERT OR REPLACE INTO music_idempotency (idempotency_key, user_id, response_json, created_at) VALUES (?, ?, ?, ?)", (key, user_id, json.dumps(response), now))
        await db.commit()




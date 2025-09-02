from __future__ import annotations

import aiosqlite
import os
import logging
from cryptography.fernet import Fernet, InvalidToken
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("MUSIC_TOKEN_DB", "music_tokens.db")
TABLE_NAME = os.getenv("MUSIC_TOKEN_TABLE", "music_tokens")
MASTER_KEY = os.getenv("MUSIC_MASTER_KEY")


def _fernet() -> Fernet | None:
    if not MASTER_KEY:
        return None
    return Fernet(MASTER_KEY.encode())


class TokenStore:
    """Encrypted token store backed by sqlite + aiosqlite using MUSIC_MASTER_KEY."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or DB_PATH

    async def _ensure_table(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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
            await db.commit()

    async def upsert_token(self, user_id: str, provider: str, access_token: bytes, refresh_token: bytes | None = None, scope: str | None = None, expires_at: int | None = None) -> None:
        f = _fernet()
        at_blob = f.encrypt(access_token) if f else access_token
        rt_blob = f.encrypt(refresh_token) if (f and refresh_token) else refresh_token
        now = int(__import__("time").time())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"INSERT OR REPLACE INTO {TABLE_NAME} (user_id, provider, access_token, refresh_token, scope, expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, provider, at_blob, rt_blob, scope, expires_at, now),
            )
            await db.commit()

    async def get_token(self, user_id: str, provider: str) -> dict | None:
        f = _fernet()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(f"SELECT access_token, refresh_token, scope, expires_at, updated_at FROM {TABLE_NAME} WHERE user_id = ? AND provider = ?", (user_id, provider))
            row = await cur.fetchone()
            if not row:
                return None
            at_blob, rt_blob, scope, expires_at, updated_at = row
            try:
                at = f.decrypt(at_blob) if (f and at_blob) else at_blob
            except InvalidToken:
                logger.exception("Failed to decrypt access token for %s@%s", user_id, provider)
                return None
            rt = None
            if rt_blob:
                try:
                    rt = f.decrypt(rt_blob) if f else rt_blob
                except InvalidToken:
                    logger.exception("Failed to decrypt refresh token for %s@%s", user_id, provider)
            return {"access_token": at, "refresh_token": rt, "scope": scope, "expires_at": expires_at, "updated_at": updated_at}

    async def delete_token(self, user_id: str, provider: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"DELETE FROM {TABLE_NAME} WHERE user_id = ? AND provider = ?", (user_id, provider))
            await db.commit()



from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import aiosqlite

DB_PATH = Path(os.getenv("USER_DB", "users.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class UserStore:
    def __init__(self, path: Path):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._path)
            # migrations table
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY
                )
                """
            )
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id TEXT PRIMARY KEY,
                    login_count INTEGER DEFAULT 0,
                    last_login TEXT,
                    request_count INTEGER DEFAULT 0
                )
                """
            )
            # record version 1
            try:
                await self._conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)")
            except Exception:
                pass
            await self._conn.commit()
        return self._conn

    async def ensure_user(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
            (user_id,),
        )
        await conn.commit()

    async def increment_login(self, user_id: str) -> None:
        conn = await self._get_conn()
        now = datetime.utcnow().isoformat()
        await conn.execute(
            """
            UPDATE user_stats
            SET login_count = login_count + 1, last_login = ?
            WHERE user_id = ?
            """,
            (now, user_id),
        )
        await conn.commit()

    async def increment_request(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE user_stats SET request_count = request_count + 1 WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()

    async def get_stats(self, user_id: str) -> dict | None:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT login_count, last_login, request_count FROM user_stats WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "login_count": row[0],
            "last_login": row[1],
            "request_count": row[2],
        }


user_store = UserStore(DB_PATH)

__all__ = ["UserStore", "user_store"]

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from .models.user_stats import UserStats


def _db_path() -> Path:
    from .db.paths import resolve_db_path
    p = resolve_db_path("USER_DB", "users.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class UserDAO:
    """Data Access Object for user statistics using SQLite."""

    def __init__(self, path: Path | None = None):
        self._path = path or _db_path()
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
                await self._conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)"
                )
            except Exception:
                pass
            await self._conn.commit()
        return self._conn

    async def ensure_schema_migrated(self) -> None:
        """Ensure the database schema is migrated."""
        await self._get_conn()  # This triggers table creation

    async def ensure_user(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
            (user_id,),
        )
        await conn.commit()

    async def increment_login(self, user_id: str) -> None:
        conn = await self._get_conn()
        now = datetime.now(UTC).isoformat()
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

    async def get_stats(self, user_id: str) -> UserStats | None:
        """Get user statistics by user ID."""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT login_count, last_login, request_count FROM user_stats WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return UserStats(
            user_id=user_id,
            login_count=row[0],
            last_login=row[1],
            request_count=row[2],
        )

    async def get_by_id(self, user_id: str) -> UserStats | None:
        """Get user statistics by user ID (alias for get_stats)."""
        return await self.get_stats(user_id)

    async def persist(self, stats: UserStats) -> bool:
        """Persist user statistics to the database."""
        try:
            conn = await self._get_conn()
            await conn.execute(
                """
                INSERT OR REPLACE INTO user_stats
                (user_id, login_count, last_login, request_count)
                VALUES (?, ?, ?, ?)
                """,
                (stats.user_id, stats.login_count, stats.last_login, stats.request_count),
            )
            await conn.commit()
            return True
        except Exception:
            return False

    async def revoke_family(self, user_id: str) -> bool:
        """Revoke/reset user statistics (not applicable for user stats)."""
        # User statistics don't have a concept of "revocation" like tokens
        # This method exists for interface consistency
        return True

    async def close(self) -> None:
        """Close persistent aiosqlite connection if open."""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass
            self._conn = None


user_dao = UserDAO(_db_path())

# Backward compatibility
UserStore = UserDAO
user_store = user_dao

__all__ = ["UserDAO", "UserStore", "user_dao", "user_store"]


# module-level helper
async def close_user_store() -> None:
    try:
        await user_dao.close()
    except Exception:
        pass

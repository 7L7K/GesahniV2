from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite


DB_PATH = os.getenv("USER_DB", "users.db")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionsStore:
    def __init__(self, path: str) -> None:
        self._path = path

    async def _get_conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._path)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_sessions (
                sid TEXT PRIMARY KEY,
                did TEXT NOT NULL,
                user_id TEXT NOT NULL,
                device_name TEXT,
                created_at TEXT,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS revoked_families (
                family_id TEXT PRIMARY KEY,
                revoked_at TEXT
            )
            """
        )
        await conn.commit()
        return conn

    async def create_session(self, user_id: str, *, did: Optional[str] = None, device_name: Optional[str] = None) -> Dict[str, str]:
        """Create a new logical login session for a device.

        Returns a dict with keys: sid, did.
        """
        sid = uuid.uuid4().hex
        if not did:
            did = uuid.uuid4().hex
        now = _utc_now_iso()
        conn = await self._get_conn()
        try:
            await conn.execute(
                "INSERT OR REPLACE INTO device_sessions (sid, did, user_id, device_name, created_at, last_seen, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (sid, did, user_id, device_name or "Web", now, now),
            )
            await conn.commit()
        finally:
            await conn.close()
        return {"sid": sid, "did": did}

    async def update_last_seen(self, sid: str) -> None:
        conn = await self._get_conn()
        try:
            await conn.execute(
                "UPDATE device_sessions SET last_seen = ? WHERE sid = ?",
                (_utc_now_iso(), sid),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def list_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        conn = await self._get_conn()
        try:
            out: List[Dict[str, Any]] = []
            async with conn.execute(
                "SELECT sid, did, device_name, created_at, last_seen, revoked FROM device_sessions WHERE user_id = ? ORDER BY last_seen DESC",
                (user_id,),
            ) as cur:
                async for row in cur:
                    out.append(
                        {
                            "sid": row[0],
                            "did": row[1],
                            "device_name": row[2],
                            "created_at": row[3],
                            "last_seen": row[4],
                            "revoked": bool(row[5]),
                        }
                    )
            return out
        finally:
            await conn.close()

    async def rename_device(self, user_id: str, did: str, new_name: str) -> bool:
        conn = await self._get_conn()
        try:
            await conn.execute(
                "UPDATE device_sessions SET device_name = ? WHERE user_id = ? AND did = ?",
                (new_name, user_id, did),
            )
            await conn.commit()
            return True
        finally:
            await conn.close()

    async def revoke_family(self, family_id: str) -> None:
        conn = await self._get_conn()
        try:
            await conn.execute(
                "INSERT OR REPLACE INTO revoked_families (family_id, revoked_at) VALUES (?, ?)",
                (family_id, _utc_now_iso()),
            )
            # Best-effort: mark matching primary session as revoked (diagnostic)
            await conn.execute(
                "UPDATE device_sessions SET revoked = 1 WHERE sid = ?",
                (family_id,),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def is_family_revoked(self, family_id: str) -> bool:
        conn = await self._get_conn()
        try:
            async with conn.execute(
                "SELECT 1 FROM revoked_families WHERE family_id = ?",
                (family_id,),
            ) as cur:
                row = await cur.fetchone()
            return bool(row)
        finally:
            await conn.close()


sessions_store = SessionsStore(DB_PATH)

__all__ = ["sessions_store", "SessionsStore"]



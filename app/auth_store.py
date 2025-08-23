from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import aiosqlite


def _compute_db_path() -> Path:
    env_path = os.getenv("AUTH_DB")
    if env_path:
        return Path(env_path).resolve()
    # Create a deterministic per-test file to avoid bleed
    if os.getenv("PYTEST_CURRENT_TEST"):
        ident = os.getenv("PYTEST_CURRENT_TEST", "")
        digest = hashlib.md5(ident.encode()).hexdigest()[:8]
        p = Path.cwd() / f".tmp_auth_{digest}.db"
    else:
        p = Path("auth.db")
    return p.resolve()


DB_PATH = _compute_db_path()
try:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


def _now() -> float:
    return time.time()


async def ensure_tables() -> None:
    # Under pytest, make sure an event loop exists for sync callers
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        if os.getenv("PYTEST_CURRENT_TEST"):
            asyncio.set_event_loop(asyncio.new_event_loop())
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        # users
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name TEXT,
                avatar_url TEXT,
                created_at REAL NOT NULL,
                verified_at REAL,
                auth_providers TEXT
            )
            """
        )
        # devices
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_name TEXT,
                ua_hash TEXT NOT NULL,
                ip_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_seen_at REAL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # sessions
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_seen_at REAL,
                revoked_at REAL,
                mfa_passed INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
            """
        )
        # oauth_identities
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_identities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL CHECK(provider IN ('google','apple')),
                provider_user_id TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(provider, provider_user_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # pat_tokens
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pat_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                scopes TEXT NOT NULL,
                exp_at REAL,
                created_at REAL NOT NULL,
                revoked_at REAL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        # audit_log
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                session_id TEXT,
                event_type TEXT NOT NULL,
                meta TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
            )
            """
        )
        await db.commit()


# ------------------------------ users ----------------------------------------
async def create_user(
    *,
    id: str,
    email: str,
    password_hash: str | None = None,
    name: str | None = None,
    avatar_url: str | None = None,
    auth_providers: list[str] | None = None,
) -> None:
    """Create or upsert a user, honoring the provided id.

    If a user already exists with the same email, update that row's id to the
    provided value along with other mutable fields. Created/verified timestamps
    are preserved on upsert.
    """
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        norm_email = (email or "").strip().lower()
        providers_json = json.dumps(auth_providers or [])
        # Transaction with deferred FK checks to allow primary-key update then child updates
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("PRAGMA defer_foreign_keys=ON")
        # Check for existing by email
        async with db.execute(
            "SELECT id FROM users WHERE email=?", (norm_email,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO users(id,email,password_hash,name,avatar_url,created_at,verified_at,auth_providers) VALUES (?,?,?,?,?,?,?,?)",
                (
                    id,
                    norm_email,
                    password_hash,
                    name,
                    avatar_url,
                    _now(),
                    None,
                    providers_json,
                ),
            )
            await db.commit()
            return
        # Exists: migrate id if different, otherwise update mutable fields
        old_id = row[0]
        if str(old_id) != str(id):
            # Update parent id first (deferred FK avoids immediate failure)
            await db.execute(
                "UPDATE users SET id=?, password_hash=COALESCE(?, password_hash), name=COALESCE(?, name), avatar_url=COALESCE(?, avatar_url), auth_providers=? WHERE email=?",
                (id, password_hash, name, avatar_url, providers_json, norm_email),
            )
            # Cascade children manually to the new id
            for table, col in (
                ("devices", "user_id"),
                ("sessions", "user_id"),
                ("oauth_identities", "user_id"),
                ("pat_tokens", "user_id"),
                ("audit_log", "user_id"),  # best-effort; nullable
            ):
                await db.execute(
                    f"UPDATE {table} SET {col}=? WHERE {col}=?", (id, old_id)
                )
            await db.commit()
            return
        # Same id: update mutable fields
        await db.execute(
            "UPDATE users SET password_hash=COALESCE(?, password_hash), name=COALESCE(?, name), avatar_url=COALESCE(?, avatar_url), auth_providers=? WHERE email=?",
            (password_hash, name, avatar_url, providers_json, norm_email),
        )
        await db.commit()


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        norm_email = (email or "").strip().lower()
        async with db.execute(
            "SELECT id,email,password_hash,name,avatar_url,created_at,verified_at,auth_providers FROM users WHERE email=?",
            (norm_email,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "name": row[3],
        "avatar_url": row[4],
        "created_at": row[5],
        "verified_at": row[6],
        "auth_providers": json.loads(row[7] or "[]"),
    }


async def verify_user(user_id: str) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("UPDATE users SET verified_at=? WHERE id=?", (_now(), user_id))
        await db.commit()


# ----------------------------- devices ---------------------------------------
async def create_device(
    *, id: str, user_id: str, device_name: str | None, ua_hash: str, ip_hash: str
) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO devices(id,user_id,device_name,ua_hash,ip_hash,created_at,last_seen_at) VALUES (?,?,?,?,?,?,?)",
            (id, user_id, device_name, ua_hash, ip_hash, _now(), _now()),
        )
        await db.commit()


async def touch_device(device_id: str) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "UPDATE devices SET last_seen_at=? WHERE id=?", (_now(), device_id)
        )
        await db.commit()


# ----------------------------- sessions --------------------------------------
async def create_session(
    *, id: str, user_id: str, device_id: str, mfa_passed: bool = False
) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO sessions(id,user_id,device_id,created_at,last_seen_at,revoked_at,mfa_passed) VALUES (?,?,?,?,?,?,?)",
            (id, user_id, device_id, _now(), _now(), None, 1 if mfa_passed else 0),
        )
        await db.commit()


async def touch_session(session_id: str) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "UPDATE sessions SET last_seen_at=? WHERE id=?", (_now(), session_id)
        )
        await db.commit()


async def revoke_session(session_id: str) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "UPDATE sessions SET revoked_at=? WHERE id=?", (_now(), session_id)
        )
        await db.commit()


# ------------------------- oauth identities ----------------------------------
async def link_oauth_identity(
    *, id: str, user_id: str, provider: str, provider_user_id: str, email: str
) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            (
                "INSERT INTO oauth_identities(id,user_id,provider,provider_user_id,email,created_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(provider, provider_user_id) DO UPDATE SET user_id=excluded.user_id, email=excluded.email"
            ),
            (id, user_id, provider, provider_user_id, email, _now()),
        )
        await db.commit()


# ---------------------------- PAT tokens -------------------------------------
async def create_pat(
    *,
    id: str,
    user_id: str,
    name: str,
    token_hash: str,
    scopes: list[str],
    exp_at: float | None = None,
) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO pat_tokens(id,user_id,name,token_hash,scopes,exp_at,created_at,revoked_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                id,
                user_id,
                name,
                token_hash,
                json.dumps(scopes or []),
                exp_at,
                _now(),
                None,
            ),
        )
        await db.commit()


async def revoke_pat(pat_id: str) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "UPDATE pat_tokens SET revoked_at=? WHERE id=?", (_now(), pat_id)
        )
        await db.commit()


async def get_pat_by_id(pat_id: str) -> dict[str, Any] | None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        async with db.execute(
            "SELECT id,user_id,name,token_hash,scopes,exp_at,created_at,revoked_at FROM pat_tokens WHERE id=?",
            (pat_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "name": row[2],
        "token_hash": row[3],
        "scopes": json.loads(row[4] or "[]"),
        "exp_at": row[5],
        "created_at": row[6],
        "revoked_at": row[7],
    }


async def get_pat_by_hash(token_hash: str) -> dict[str, Any] | None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        async with db.execute(
            "SELECT id,user_id,name,token_hash,scopes,exp_at,created_at,revoked_at FROM pat_tokens WHERE token_hash=?",
            (token_hash,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "name": row[2],
        "token_hash": row[3],
        "scopes": json.loads(row[4] or "[]"),
        "exp_at": row[5],
        "created_at": row[6],
        "revoked_at": row[7],
    }


async def list_pats_for_user(user_id: str) -> list[dict[str, Any]]:
    """List all PATs for a user, returning safe fields only (no token hash)."""
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        async with db.execute(
            "SELECT id,name,scopes,created_at,revoked_at FROM pat_tokens WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "scopes": json.loads(row[2] or "[]"),
            "created_at": row[3],
            "revoked_at": row[4],
        }
        for row in rows
    ]


# ---------------------------- audit log --------------------------------------
async def record_audit(
    *,
    id: str,
    user_id: str | None,
    session_id: str | None,
    event_type: str,
    meta: dict[str, Any] | None = None,
) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO audit_log(id,user_id,session_id,event_type,meta,created_at) VALUES (?,?,?,?,?,?)",
            (id, user_id, session_id, event_type, json.dumps(meta or {}), _now()),
        )
        await db.commit()


__all__ = [
    "ensure_tables",
    # users
    "create_user",
    "get_user_by_email",
    "verify_user",
    # devices
    "create_device",
    "touch_device",
    # sessions
    "create_session",
    "touch_session",
    "revoke_session",
    # oauth
    "link_oauth_identity",
    # pat
    "create_pat",
    "revoke_pat",
    "get_pat_by_hash",
    "get_pat_by_id",
    "list_pats_for_user",
    # audit
    "record_audit",
]

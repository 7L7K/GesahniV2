from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import time_ns
from typing import Any

logger = logging.getLogger(__name__)

# Base directory for session metadata and media
SESSIONS_DIR = Path(
    os.getenv("SESSIONS_DIR", Path(__file__).parent.parent / "sessions")
)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class SessionStatus(str, Enum):
    """Lifecycle states for a captured session."""

    PENDING = "PENDING"
    PROCESSING_WHISPER = "PROCESSING_WHISPER"
    TRANSCRIBED = "TRANSCRIBED"
    PROCESSING_GPT = "PROCESSING_GPT"
    DONE = "DONE"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Session Cookie Store (for __session cookie management)
# ---------------------------------------------------------------------------


class SessionStoreUnavailable(Exception):
    """Raised when the configured session store backend is unavailable."""


class SessionCookieStore:
    """Store for mapping __session cookie IDs to access token JTIs.

    Creates, reads, and deletes opaque session IDs that are stored in the __session cookie.
    Uses Redis if available, falls back to in-memory storage for development/testing.

    The session ID is always opaque (never a JWT) and maps to the JWT ID (JTI) from the access token.
    """

    def __init__(self):
        self._redis_client = None
        # In-memory fallback
        # session_id -> payload dict
        # Legacy entries may be stored as tuple (jti, expires_at)
        self._memory_store: dict[str, Any] = {}
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis client if available."""
        try:
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                from redis import Redis

                self._redis_client = Redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self._redis_client.ping()
                logger.info("Session store using Redis backend")
            else:
                logger.info("Session store using in-memory backend (no REDIS_URL)")
        except Exception as e:
            logger.warning(f"Redis unavailable for session store, using in-memory: {e}")
            self._redis_client = None

    def _get_key(self, session_id: str) -> str:
        """Get Redis key for session."""
        return f"session:{session_id}"

    def create_session(self, jti: str, expires_at: float, *, identity: dict | None = None, refresh_fam_id: str | None = None) -> str:
        """Create a new opaque session ID and store it mapped to the JTI.

        Args:
            jti: JWT ID from access token
            expires_at: Unix timestamp when session expires

        Returns:
            str: New opaque session ID (never a JWT)
        """
        # Generate opaque session ID: sess_timestamp_random
        session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

        payload = {
            "jti": jti,
            "expires_at": float(expires_at),
        }
        if identity and isinstance(identity, dict):
            # Normalize minimal identity fields
            ident = identity.copy()
            if "user_id" not in ident and ident.get("sub"):
                ident["user_id"] = ident.get("sub")
            if "sub" not in ident and ident.get("user_id"):
                ident["sub"] = ident.get("user_id")
            ident.setdefault("jti", jti)
            ident.setdefault("exp", int(expires_at))
            ident.setdefault("scopes", identity.get("scopes") or identity.get("scope") or [])
            now_s = int(time.time())
            payload.update(
                {
                    "identity": ident,
                    "created_at": now_s,
                    "last_seen_at": now_s,
                }
            )
            if refresh_fam_id:
                payload["refresh_fam_id"] = refresh_fam_id

        ttl = int(min(float(expires_at) - time.time(), 30 * 24 * 3600))
        ttl = max(ttl, 1)

        if self._redis_client:
            try:
                # Store in Redis with TTL
                self._redis_client.setex(
                    self._get_key(session_id),
                    ttl,
                    json.dumps(payload),
                )
            except Exception as e:
                # Surface as outage for callers that may want to 503 session-only flows
                logger.warning(f"Redis unavailable during create_session: {e}")
                raise SessionStoreUnavailable(str(e))
        else:
            # Store in memory
            self._memory_store[session_id] = payload

        logger.debug(f"Created opaque session {session_id} for JTI {jti}")
        return session_id

    def get_session(self, session_id: str) -> str | None:
        """Get the JTI for an opaque session ID.

        Args:
            session_id: Opaque session ID from __session cookie

        Returns:
            str: JTI if session exists and is valid, None otherwise
        """
        if self._redis_client:
            try:
                data = self._redis_client.get(self._get_key(session_id))
                if data:
                    session_data = json.loads(data)
                    if session_data.get("expires_at", 0) > time.time():
                        return session_data.get("jti")
                    else:
                        # Expired, clean up
                        self._redis_client.delete(self._get_key(session_id))
            except Exception as e:
                logger.warning(f"Redis error getting session {session_id}: {e}")
                raise SessionStoreUnavailable(str(e))
        else:
            # Check in-memory store
            if session_id in self._memory_store:
                entry = self._memory_store[session_id]
                if isinstance(entry, tuple):
                    # Legacy tuple format
                    jti, expires_at = entry
                    if expires_at > time.time():
                        return jti
                    del self._memory_store[session_id]
                elif isinstance(entry, dict):
                    if float(entry.get("expires_at", 0)) > time.time():
                        return entry.get("jti")
                    del self._memory_store[session_id]

        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete an opaque session ID.

        Args:
            session_id: Opaque session ID to delete

        Returns:
            bool: True if session was deleted, False if not found
        """
        if self._redis_client:
            try:
                return bool(self._redis_client.delete(self._get_key(session_id)))
            except Exception as e:
                logger.warning(f"Redis error deleting session {session_id}: {e}")
                raise SessionStoreUnavailable(str(e))
        else:
            if session_id in self._memory_store:
                del self._memory_store[session_id]
                return True
            return False

    def cleanup_expired(self):
        """Clean up expired sessions from memory store."""
        if not self._redis_client:
            current_time = time.time()
            expired = [
                sid
                for sid, entry in self._memory_store.items()
                if (
                    (isinstance(entry, tuple) and entry[1] <= current_time)
                    or (isinstance(entry, dict) and float(entry.get("expires_at", 0)) <= current_time)
                )
            ]
            for sid in expired:
                del self._memory_store[sid]
            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired sessions")

    # -----------------------------
    # Identity store (Phase 1)
    # -----------------------------

    def set_session_identity(
        self,
        session_id: str,
        identity: dict,
        exp_s: int,
        refresh_fam_id: str | None = None,
    ) -> None:
        """Persist identity for a session with safe TTL.

        TTL is min(exp_s-now, 30d). Never raises on in-memory backend.
        """
        now = int(time.time())
        ttl = max(1, min(int(exp_s - now), 30 * 24 * 3600))
        # Normalize identity
        ident = identity.copy()
        if "user_id" not in ident and ident.get("sub"):
            ident["user_id"] = ident.get("sub")
        if "sub" not in ident and ident.get("user_id"):
            ident["sub"] = ident.get("user_id")
        jti = ident.get("jti") or ""
        payload = {
            "jti": jti,
            "expires_at": float(exp_s),
            "identity": ident,
            "created_at": now,
            "last_seen_at": now,
        }
        if refresh_fam_id:
            payload["refresh_fam_id"] = refresh_fam_id

        if self._redis_client:
            try:
                self._redis_client.setex(
                    self._get_key(session_id), ttl, json.dumps(payload)
                )
            except Exception as e:
                logger.warning(
                    f"Redis unavailable during set_session_identity for {session_id}: {e}"
                )
                raise SessionStoreUnavailable(str(e))
        else:
            self._memory_store[session_id] = payload

    def get_session_identity(self, session_id: str) -> dict | None:
        """Return identity payload for a session if present and not expired."""
        if self._redis_client:
            try:
                data = self._redis_client.get(self._get_key(session_id))
                if not data:
                    return None
                obj = json.loads(data)
                if float(obj.get("expires_at", 0)) <= time.time():
                    self._redis_client.delete(self._get_key(session_id))
                    return None
                return obj.get("identity")
            except Exception as e:
                logger.warning(f"Redis error get_session_identity {session_id}: {e}")
                raise SessionStoreUnavailable(str(e))
        else:
            entry = self._memory_store.get(session_id)
            if not entry:
                return None
            if isinstance(entry, tuple):
                # Legacy format has no identity
                return None
            if float(entry.get("expires_at", 0)) <= time.time():
                self._memory_store.pop(session_id, None)
                return None
            return entry.get("identity")

    def touch_session(self, session_id: str, exp_s: int) -> None:
        """Update last_seen_at and extend TTL (bounded) when appropriate."""
        now = int(time.time())
        ttl = max(1, min(int(exp_s - now), 30 * 24 * 3600))
        if self._redis_client:
            try:
                data = self._redis_client.get(self._get_key(session_id))
                if not data:
                    return
                obj = json.loads(data)
                obj["last_seen_at"] = now
                self._redis_client.setex(
                    self._get_key(session_id), ttl, json.dumps(obj)
                )
            except Exception as e:
                logger.warning(f"Redis error touch_session {session_id}: {e}")
                raise SessionStoreUnavailable(str(e))
        else:
            entry = self._memory_store.get(session_id)
            if isinstance(entry, dict):
                entry["last_seen_at"] = now
                self._memory_store[session_id] = entry

    def revoke_session(self, session_id: str) -> None:
        """Remove session from the store."""
        _ = self.delete_session(session_id)


# Global session store instance
_session_store = SessionCookieStore()


def get_session_store() -> SessionCookieStore:
    """Get the global session store instance."""
    return _session_store


# ---------------------------------------------------------------------------
# Basic file helpers
# ---------------------------------------------------------------------------


def session_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def meta_path(session_id: str) -> Path:
    return session_path(session_id) / "meta.json"


def load_meta(session_id: str) -> dict[str, Any]:
    mp = meta_path(session_id)
    if mp.exists():
        return json.loads(mp.read_text(encoding="utf-8"))
    return {}


def save_meta(session_id: str, meta: dict[str, Any]) -> None:
    mp = meta_path(session_id)

    # Create the session directory if it doesn't exist
    mp.parent.mkdir(parents=True, exist_ok=True)

    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------


def create_session() -> dict[str, Any]:
    """Create a new session entry and return its metadata."""
    ts = datetime.utcnow().isoformat(timespec="seconds")
    session_id = f"{time_ns()}_{random.getrandbits(12):03x}"
    meta = {
        "session_id": session_id,
        "created_at": ts + "Z",
        "status": SessionStatus.PENDING.value,
        "retry_count": 0,
        "errors": [],
    }
    save_meta(session_id, meta)
    return meta


def update_session(session_id: str, **fields: Any) -> dict[str, Any]:
    meta = load_meta(session_id)
    meta.update(fields)
    save_meta(session_id, meta)
    return meta


def update_status(session_id: str, status: SessionStatus) -> dict[str, Any]:
    return update_session(session_id, status=status.value)


def append_error(session_id: str, error: str) -> dict[str, Any]:
    meta = load_meta(session_id)
    meta.setdefault("errors", []).append(error)
    save_meta(session_id, meta)
    return meta


def get_session(session_id: str) -> dict[str, Any]:
    return load_meta(session_id)


def list_sessions(status: SessionStatus | None = None) -> list[dict[str, Any]]:
    sessions = []
    for session_dir in SESSIONS_DIR.iterdir():
        if session_dir.is_dir():
            meta = load_meta(session_dir.name)
            if meta and (status is None or meta.get("status") == status.value):
                sessions.append(meta)
    return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)


__all__ = [
    "SESSIONS_DIR",
    "SessionStatus",
    "session_path",
    "meta_path",
    "load_meta",
    "save_meta",
    "create_session",
    "update_session",
    "update_status",
    "append_error",
    "get_session",
    "list_sessions",
    "get_session_store",
    "SessionStoreUnavailable",
]

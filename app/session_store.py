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


class SessionCookieStore:
    """Store for mapping __session cookie IDs to access token JTIs.

    Creates, reads, and deletes opaque session IDs that are stored in the __session cookie.
    Uses Redis if available, falls back to in-memory storage for development/testing.

    The session ID is always opaque (never a JWT) and maps to the JWT ID (JTI) from the access token.
    """

    def __init__(self):
        self._redis_client = None
        self._memory_store = {}  # session_id -> (jti, expires_at)
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

    def create_session(self, jti: str, expires_at: float) -> str:
        """Create a new opaque session ID and store it mapped to the JTI.

        Args:
            jti: JWT ID from access token
            expires_at: Unix timestamp when session expires

        Returns:
            str: New opaque session ID (never a JWT)
        """
        # Generate opaque session ID: sess_timestamp_random
        session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

        if self._redis_client:
            # Store in Redis with TTL
            ttl = int(expires_at - time.time())
            if ttl > 0:
                self._redis_client.setex(
                    self._get_key(session_id),
                    ttl,
                    json.dumps({"jti": jti, "expires_at": expires_at}),
                )
        else:
            # Store in memory
            self._memory_store[session_id] = (jti, expires_at)

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
                    if session_data["expires_at"] > time.time():
                        return session_data["jti"]
                    else:
                        # Expired, clean up
                        self._redis_client.delete(self._get_key(session_id))
            except Exception as e:
                logger.warning(f"Redis error getting session {session_id}: {e}")
        else:
            # Check in-memory store
            if session_id in self._memory_store:
                jti, expires_at = self._memory_store[session_id]
                if expires_at > time.time():
                    return jti
                else:
                    # Expired, clean up
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
                return False
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
                for sid, (_, expires_at) in self._memory_store.items()
                if expires_at <= current_time
            ]
            for sid in expired:
                del self._memory_store[sid]
            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired sessions")


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
]

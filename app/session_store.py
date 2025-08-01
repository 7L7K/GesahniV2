from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List

# Base directory for session metadata and media
SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", Path(__file__).parent.parent / "sessions"))
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
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------


def create_session() -> dict[str, Any]:
    """Create a new session entry and return its metadata."""
    ts = datetime.utcnow().isoformat(timespec="seconds")
    session_id = ts.replace(":", "-")
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
    errors = meta.setdefault("errors", [])
    errors.append(error)
    retry = meta.get("retry_count", 0) + 1
    meta["retry_count"] = retry
    save_meta(session_id, meta)
    return meta


def get_session(session_id: str) -> dict[str, Any]:
    return load_meta(session_id)


def list_sessions(status: SessionStatus | None = None) -> List[dict[str, Any]]:
    """Return all sessions, optionally filtering by ``status``."""
    sessions: List[dict[str, Any]] = []
    for d in SESSIONS_DIR.iterdir():
        if not d.is_dir():
            continue
        meta = load_meta(d.name)
        if not meta:
            continue
        if status is None or meta.get("status") == status.value:
            sessions.append(meta)
    sessions.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return sessions


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
]

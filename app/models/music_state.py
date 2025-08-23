from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

_TEST_MODE = (
    bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_RUNNING"))
    or os.getenv("ENV", "").lower() == "test"
    or os.getenv("JWT_OPTIONAL_IN_TESTS", "0").lower() in {"1", "true", "yes", "on"}
)
DB_PATH = os.getenv("MUSIC_DB") or ("sqlite:///:memory:" if _TEST_MODE else "music.db")


def _connect() -> sqlite3.Connection:
    if DB_PATH.startswith("sqlite://"):
        path = DB_PATH[len("sqlite://") :]
        if path.startswith("/"):
            path = path[1:]
        return sqlite3.connect(path or ":memory:", check_same_thread=False)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


_conn = _connect()
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS music_state (
        user_id TEXT PRIMARY KEY,
        state_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """
)
_conn.commit()

# In test mode, ensure the table is empty at import so defaults apply predictably
if _TEST_MODE:
    try:
        _conn.execute("DELETE FROM music_state")
        _conn.commit()
    except Exception:
        pass


@dataclass
class MusicVibe:
    name: str
    energy: float  # 0.0 - 1.0
    tempo: float   # bpm hint
    explicit: bool


@dataclass
class MusicState:
    # Minimal state persisted per user
    vibe: MusicVibe
    volume: int = 40
    device_id: str | None = None
    last_track_id: str | None = None
    last_recommendations: list[dict] | None = None
    recs_cached_at: float | None = None
    duck_from: int | None = None
    quiet_hours: bool = False
    explicit_allowed: bool = True
    radio_playing: bool = True  # fallback radio stream when Spotify disabled
    skip_count: int = 0

    @staticmethod
    def default() -> MusicState:
        return MusicState(
            vibe=MusicVibe(name="Calm Night", energy=0.25, tempo=80, explicit=False),
            volume=25,
            device_id=None,
            last_track_id=None,
            last_recommendations=None,
            duck_from=None,
            quiet_hours=False,
            explicit_allowed=False,
        )


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def load_state(user_id: str) -> MusicState:
    cur = _conn.execute("SELECT state_json FROM music_state WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        st = MusicState.default()
        save_state(user_id, st)
        return st
    try:
        data = json.loads(row[0])
        vibe = data.get("vibe") or {}
        ms = MusicState(
            vibe=MusicVibe(
                name=vibe.get("name", "Calm Night"),
                energy=float(vibe.get("energy", 0.25)),
                tempo=float(vibe.get("tempo", 80)),
                explicit=bool(vibe.get("explicit", False)),
            ),
            volume=int(data.get("volume", 25)),
            device_id=data.get("device_id"),
            last_track_id=data.get("last_track_id"),
            last_recommendations=data.get("last_recommendations") or None,
            recs_cached_at=float(data.get("recs_cached_at")) if data.get("recs_cached_at") is not None else None,
            duck_from=data.get("duck_from"),
            quiet_hours=bool(data.get("quiet_hours", False)),
            explicit_allowed=bool(data.get("explicit_allowed", True)),
            radio_playing=bool(data.get("radio_playing", True)),
            skip_count=int(data.get("skip_count", 0)),
        )
        return ms
    except Exception:
        return MusicState.default()


def save_state(user_id: str, state: MusicState) -> None:
    payload: dict[str, Any] = {
        "vibe": asdict(state.vibe),
        "volume": int(state.volume),
        "device_id": state.device_id,
        "last_track_id": state.last_track_id,
        "last_recommendations": state.last_recommendations,
        "recs_cached_at": state.recs_cached_at,
        "duck_from": state.duck_from,
        "quiet_hours": state.quiet_hours,
        "explicit_allowed": state.explicit_allowed,
        "radio_playing": state.radio_playing,
        "skip_count": int(state.skip_count),
    }
    js = json.dumps(payload, ensure_ascii=False)
    _conn.execute(
        "INSERT INTO music_state(user_id, state_json, updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
        (user_id, js, _now_iso()),
    )
    _conn.commit()


__all__ = ["MusicState", "MusicVibe", "load_state", "save_state"]



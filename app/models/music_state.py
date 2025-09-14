from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

# Lightweight in-memory state for music to avoid legacy file-backed store dependency in app/
_STATE: dict[str, str] = {}


@dataclass
class MusicVibe:
    name: str
    energy: float  # 0.0 - 1.0
    tempo: float  # bpm hint
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
    return datetime.now(UTC).isoformat()


def load_state(user_id: str) -> MusicState:
    js = _STATE.get(user_id)
    if js is None:
        st = MusicState.default()
        save_state(user_id, st)
        return st
    try:
        data = json.loads(js)
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
            recs_cached_at=(
                float(data.get("recs_cached_at"))
                if data.get("recs_cached_at") is not None
                else None
            ),
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
    _STATE[user_id] = js


__all__ = ["MusicState", "MusicVibe", "load_state", "save_state"]

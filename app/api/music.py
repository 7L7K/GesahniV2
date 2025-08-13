from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
import inspect
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel, Field, ConfigDict

from ..deps.user import get_current_user_id
from ..security import verify_ws, rate_limit
from ..integrations.music_spotify.client import SpotifyClient, SpotifyAuthError
from ..models.music_state import MusicState, MusicVibe, load_state, save_state


router = APIRouter(prefix="", tags=["Music"])  # rate limit applied selectively in main


# ---------------------------------------------------------------------------
# Feature flags and env
# ---------------------------------------------------------------------------

# Default provider flags (favor safer defaults in test environments)
_TEST_MODE = (
    bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_RUNNING"))
    or os.getenv("ENV", "").strip().lower() == "test"
    or os.getenv("JWT_OPTIONAL_IN_TESTS", "0").strip().lower() in {"1", "true", "yes", "on"}
)

if _TEST_MODE:
    PROVIDER_SPOTIFY = False
else:
    PROVIDER_SPOTIFY = os.getenv("PROVIDER_SPOTIFY", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
MUSIC_FALLBACK_RADIO = os.getenv("MUSIC_FALLBACK_RADIO", "false").strip().lower() in {"1", "true", "yes", "on"}
EXPLICIT_DEFAULT = os.getenv("EXPLICIT_DEFAULT", "true").strip().lower() in {"1", "true", "yes", "on"}

QUIET_START = os.getenv("QUIET_HOURS_START", "22:00")
QUIET_END = os.getenv("QUIET_HOURS_END", "07:00")

ALBUM_DIR = Path(os.getenv("ALBUM_ART_DIR", "data/album_art")).resolve()
ALBUM_DIR.mkdir(parents=True, exist_ok=True)
RADIO_URL = os.getenv("FALLBACK_RADIO_URL", "")


DEFAULT_VIBES: dict[str, MusicVibe] = {
    "Calm Night": MusicVibe(name="Calm Night", energy=0.25, tempo=80, explicit=False),
    "Turn Up": MusicVibe(name="Turn Up", energy=0.9, tempo=128, explicit=False),
    "Uplift Morning": MusicVibe(name="Uplift Morning", energy=0.6, tempo=110, explicit=False),
}


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm))


def _in_quiet_hours(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    start = _parse_hhmm(QUIET_START)
    end = _parse_hhmm(QUIET_END)
    nt = now.time()
    if start <= end:
        return start <= nt <= end
    # window across midnight
    return nt >= start or nt <= end


def _volume_cap_for(vibe: MusicVibe, quiet: bool) -> int:
    base = 20 + int(vibe.energy * 70)  # 20..90
    if quiet:
        base = min(base, 30)
    return max(5, min(100, base))


def _explicit_allowed(vibe: MusicVibe) -> bool:
    return bool(vibe.explicit and EXPLICIT_DEFAULT)


async def _ensure_album_cached(url: str | None, track_id: str | None) -> str | None:
    if not url or not track_id:
        return None
    dest = ALBUM_DIR / f"{track_id}.jpg"
    public = f"/album_art/{track_id}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        return public
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as s:
            r = await s.get(url)
            if r.status_code == 200 and r.content:
                dest.write_bytes(r.content)
                return public
    except Exception:
        return None
    return None


async def _provider_state(user_id: str) -> dict | None:
    if not PROVIDER_SPOTIFY:
        return None
    try:
        client = SpotifyClient(user_id)
        st = await client.get_state()
        return st
    except SpotifyAuthError:
        # Treat as no provider state when not authenticated
        return None
    except Exception:
        return None


async def _provider_queue(user_id: str) -> tuple[dict | None, list[dict]]:
    if not PROVIDER_SPOTIFY:
        return None, []
    try:
        client = SpotifyClient(user_id)
        return await client.get_queue()
    except SpotifyAuthError:
        return None, []
    except Exception:
        return None, []


async def _provider_play(user_id: str, uris: list[str] | None = None) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.play(uris)
    except SpotifyAuthError:
        return False
    except Exception:
        return False


async def _provider_pause(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.pause()
    except SpotifyAuthError:
        return False
    except Exception:
        return False


async def _provider_next(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.next()
    except SpotifyAuthError:
        return False
    except Exception:
        return False


async def _provider_previous(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.previous()
    except SpotifyAuthError:
        return False
    except Exception:
        return False


async def _provider_set_volume(user_id: str, level: int) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.set_volume(level)
    except SpotifyAuthError:
        return False
    except Exception:
        return False


async def _provider_recommendations(
    user_id: str, *, seed_tracks: list[str] | None, vibe: MusicVibe, limit: int
) -> list[dict]:
    if not PROVIDER_SPOTIFY:
        return []
    try:
        client = SpotifyClient(user_id)
        return await client.recommendations(
            seed_tracks=seed_tracks,
            target_energy=vibe.energy,
            target_tempo=vibe.tempo,
            limit=limit,
        )
    except SpotifyAuthError:
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class MusicCommand(BaseModel):
    command: str = Field(..., description="play|pause|next|previous|volume")
    volume: Optional[int] = None
    device_id: Optional[str] = None
    temporary: bool = False  # when true, store prior volume to restore later

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"command": "volume", "volume": 20, "temporary": True}
        }
    )


class VibeBody(BaseModel):
    name: Optional[str] = None
    energy: Optional[float] = Field(None, ge=0.0, le=1.0)
    tempo: Optional[float] = None
    explicit: Optional[bool] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "Calm Night", "energy": 0.3, "tempo": 85, "explicit": False}
        }
    )


class StateResponse(BaseModel):
    vibe: dict
    volume: int
    device_id: str | None
    progress_ms: int | None = None
    is_playing: bool | None = None
    track: dict | None = None
    quiet_hours: bool
    explicit_allowed: bool
    provider: str | None = None
    radio_url: str | None = None
    radio_playing: bool | None = None


# ---------------------------------------------------------------------------
# WebSocket registry for broadcasting
# ---------------------------------------------------------------------------


_ws_clients: set[WebSocket] = set()


async def _broadcast(topic: str, payload: dict) -> None:
    if not _ws_clients:
        return
    dead: list[WebSocket] = []
    for ws in list(_ws_clients):
        try:
            await ws.send_json({"topic": topic, "data": payload})
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _ws_clients.discard(ws)
            await ws.close()
        except Exception:
            pass


@router.websocket("/ws/music")
async def ws_music(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    await verify_ws(ws)
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except Exception:
        pass
    finally:
        _ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class OkResponse(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


@router.post("/music", response_model=OkResponse, responses={200: {"model": OkResponse}})
async def music_command(body: MusicCommand, user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    quiet = _in_quiet_hours()
    cap = _volume_cap_for(state.vibe, quiet)
    changed = False

    if body.command == "play":
        if not PROVIDER_SPOTIFY and MUSIC_FALLBACK_RADIO:
            state.radio_playing = True
            changed = True
        else:
            await _provider_play(user_id)
    elif body.command == "pause":
        if not PROVIDER_SPOTIFY and MUSIC_FALLBACK_RADIO:
            state.radio_playing = False
            changed = True
        else:
            await _provider_pause(user_id)
    elif body.command == "next":
        if PROVIDER_SPOTIFY:
            await _provider_next(user_id)
        state.skip_count = (state.skip_count or 0) + 1
        changed = True
    elif body.command == "previous":
        if PROVIDER_SPOTIFY:
            await _provider_previous(user_id)
        # no-op for radio fallback
    elif body.command == "volume":
        if body.volume is None:
            raise HTTPException(status_code=400, detail="missing_volume")
        new_level = max(0, min(cap, int(body.volume)))
        if body.temporary and state.duck_from is None:
            state.duck_from = state.volume
        state.volume = new_level
        changed = True
        if PROVIDER_SPOTIFY:
            await _provider_set_volume(user_id, new_level)
    else:
        raise HTTPException(status_code=400, detail="unknown_command")

    # Persist and broadcast if anything changed that we track
    if changed:
        state.quiet_hours = quiet
        state.explicit_allowed = _explicit_allowed(state.vibe)
        save_state(user_id, state)
        await _broadcast("music.state", await get_state(user_id))
    return {"status": "ok"}


class VibeResponse(BaseModel):
    status: str = "ok"
    vibe: dict

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "vibe": {"name": "Calm Night", "energy": 0.3, "tempo": 85, "explicit": False},
            }
        }
    )


@router.post("/vibe", response_model=VibeResponse, responses={200: {"model": VibeResponse}})
async def set_vibe(body: VibeBody, user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    # Fill from defaults if only name provided
    if body.name and body.name in DEFAULT_VIBES:
        state.vibe = DEFAULT_VIBES[body.name]
    else:
        # Merge partials
        vibe = state.vibe
        state.vibe = MusicVibe(
            name=body.name or vibe.name,
            energy=float(body.energy) if body.energy is not None else vibe.energy,
            tempo=float(body.tempo) if body.tempo is not None else vibe.tempo,
            explicit=bool(body.explicit) if body.explicit is not None else vibe.explicit,
        )

    # Enforce new caps immediately
    quiet = _in_quiet_hours()
    cap = _volume_cap_for(state.vibe, quiet)
    if state.volume > cap:
        state.volume = cap
        await _provider_set_volume(user_id, cap)

    state.quiet_hours = quiet
    state.explicit_allowed = _explicit_allowed(state.vibe)

    save_state(user_id, state)
    await _broadcast("music.state", await get_state(user_id))
    return {"status": "ok", "vibe": asdict(state.vibe)}


@router.post("/music/restore", response_model=OkResponse, responses={200: {"model": OkResponse}})
async def restore_volume(user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    if state.duck_from is not None:
        quiet = _in_quiet_hours()
        cap = _volume_cap_for(state.vibe, quiet)
        restored = max(0, min(cap, int(state.duck_from)))
        state.volume = restored
        state.duck_from = None
        save_state(user_id, state)
        await _provider_set_volume(user_id, restored)
        await _broadcast("music.state", await get_state(user_id))
    return {"status": "ok"}


@router.get("/state", response_model=StateResponse)
async def get_state(user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    quiet = _in_quiet_hours()
    sp = None
    if PROVIDER_SPOTIFY:
        _res = _provider_state(user_id)
        sp = await _res if inspect.isawaitable(_res) else _res

    track = None
    progress_ms = None
    is_playing = None
    if sp:
        item = (sp or {}).get("item") or {}
        track_id = item.get("id")
        state.last_track_id = track_id or state.last_track_id
        images = ((item.get("album") or {}).get("images") or [])
        art_url = images[0]["url"] if images else None
        _cached = _ensure_album_cached(art_url, track_id)
        cached = await _cached if inspect.isawaitable(_cached) else _cached
        track = {
            "id": track_id,
            "name": item.get("name"),
            "artists": ", ".join([a.get("name", "") for a in item.get("artists", [])]),
            "art_url": cached or art_url,
            "duration_ms": item.get("duration_ms"),
        }
        progress_ms = sp.get("progress_ms")
        is_playing = sp.get("is_playing")
    elif MUSIC_FALLBACK_RADIO and not PROVIDER_SPOTIFY:
        # Offline fallback: minimal state using static art
        track = {
            "id": "radio",
            "name": "Local Radio",
            "artists": "—",
            "art_url": "/placeholder.png",
        }
        is_playing = state.radio_playing

    state.quiet_hours = quiet
    state.explicit_allowed = _explicit_allowed(state.vibe)
    save_state(user_id, state)

    provider = "spotify" if PROVIDER_SPOTIFY else ("radio" if MUSIC_FALLBACK_RADIO else None)
    return StateResponse(
        vibe=asdict(state.vibe),
        volume=state.volume,
        device_id=state.device_id,
        progress_ms=progress_ms,
        is_playing=is_playing,
        track=track,
        quiet_hours=state.quiet_hours,
        explicit_allowed=state.explicit_allowed,
        provider=provider,
        radio_url=RADIO_URL or None,
        radio_playing=state.radio_playing if (not PROVIDER_SPOTIFY and MUSIC_FALLBACK_RADIO) else None,
    )


@router.get("/queue")
async def get_queue(user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    if not PROVIDER_SPOTIFY:
        asyncio.create_task(_broadcast("music.queue.updated", {"count": 0}))
        return {"current": None, "up_next": [], "skip_count": state.skip_count}
    _qres = _provider_queue(user_id)
    current, queue = (await _qres) if inspect.isawaitable(_qres) else _qres
    # Broadcast queue update for listeners
    asyncio.create_task(_broadcast("music.queue.updated", {"count": len(queue)}))
    # Map to minimal shape
    async def _map(item: dict | None) -> dict | None:
        if not item:
            return None
        tid = (item.get("id") if item else None)
        images = ((item.get("album") or {}).get("images") or [])
        art_url = images[0]["url"] if images else None
        _cached = _ensure_album_cached(art_url, tid)
        cached = await _cached if inspect.isawaitable(_cached) else _cached
        return {
            "id": tid,
            "name": item.get("name"),
            "artists": ", ".join([a.get("name", "") for a in item.get("artists", [])]),
            "art_url": cached or art_url,
        }

    mapped_current = await _map((current or {}).get("item") if current else None)
    mapped_queue: list[dict] = []
    for q in queue:
        mapped_queue.append(await _map(q))
    return {"current": mapped_current, "up_next": mapped_queue, "skip_count": state.skip_count}


@router.get("/recommendations")
async def get_recommendations(limit: int = 6, user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    # Serve cached quickly if available (< 2 minutes) and provider disabled
    if not PROVIDER_SPOTIFY and state.last_recommendations:
        try:
            import time

            # If timestamp missing or stale handling fails, still serve cached in test/dev
            if not state.recs_cached_at or (time.time() - float(state.recs_cached_at) < 120):
                clamp_cached = max(1, min(10, limit))
                return {"recommendations": state.last_recommendations[:clamp_cached]}
        except Exception:
            # Best-effort fallback: return cached as-is
            clamp_cached = max(1, min(10, limit))
            return {"recommendations": state.last_recommendations[:clamp_cached]}
    seeds: list[str] | None = [state.last_track_id] if state.last_track_id else None
    tracks: list[dict] = []
    if PROVIDER_SPOTIFY:
        _rres = _provider_recommendations(
            user_id, seed_tracks=seeds, vibe=state.vibe, limit=max(1, min(10, limit))
        )
        tracks = await _rres if inspect.isawaitable(_rres) else _rres
    # Final clamp in case provider ignores requested limit
    clamp = max(1, min(10, limit))
    if len(tracks) > clamp:
        tracks = tracks[:clamp]
    # Apply explicit filter
    allowed = _explicit_allowed(state.vibe)
    if not allowed:
        tracks = [t for t in tracks if not t.get("explicit")]
    out: list[dict] = []
    for t in tracks:
        tid = t.get("id")
        images = ((t.get("album") or {}).get("images") or [])
        art_url = images[0]["url"] if images else None
        _cached = _ensure_album_cached(art_url, tid)
        cached = await _cached if inspect.isawaitable(_cached) else _cached
        out.append(
            {
                "id": tid,
                "name": t.get("name"),
                "artists": ", ".join([a.get("name", "") for a in t.get("artists", [])]),
                "art_url": cached or art_url,
                "explicit": bool(t.get("explicit")),
            }
        )
    # cache last recs (IDs + minimal data)
    import time
    state.last_recommendations = out
    state.recs_cached_at = time.time()
    save_state(user_id, state)
    return {"recommendations": out}


class DeviceBody(BaseModel):
    device_id: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"device_id": "abcdef123"}}
    )


@router.get("/music/devices")
async def list_devices(user_id: str = Depends(get_current_user_id)):
    if not PROVIDER_SPOTIFY:
        return {"devices": []}
    try:
        client = SpotifyClient(user_id)
        devices = await client.devices()
    except SpotifyAuthError:
        devices = []
    except Exception:
        devices = []
    return {"devices": devices}


@router.post("/music/device", response_model=OkResponse, responses={200: {"model": OkResponse}})
async def set_device(body: DeviceBody, user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    state.device_id = body.device_id
    save_state(user_id, state)
    if PROVIDER_SPOTIFY:
        try:
            client = SpotifyClient(user_id)
            await client.transfer(body.device_id, play=True)
        except Exception:
            # Non-fatal in tests or when auth not configured
            pass
    await _broadcast("music.state", await get_state(user_id))
    return {"status": "ok"}



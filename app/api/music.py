from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..deps.user import get_current_user_id
from ..music.orchestrator import MusicOrchestrator
from ..music.providers.spotify_provider import SpotifyProvider
from ..music.store import get_idempotent, set_idempotent

router = APIRouter(prefix="/api/music")

# Also create a root-level router for endpoints that should be at /v1/state
root_router = APIRouter()
logger = logging.getLogger(__name__)


class PlayBody(BaseModel):
    utterance: str | None = None
    entity: dict | None = None
    room: str | None = None
    vibe: str | None = None
    provider_hint: str | None = None


@router.post("/play")
async def play(body: PlayBody, request: Request, user_id: str = Depends(get_current_user_id)):
    # idempotency
    key = request.headers.get("X-Idempotency-Key")
    if key:
        prev = await get_idempotent(key, user_id)
        if prev:
            return prev
    provider = SpotifyProvider()
    orch = MusicOrchestrator(providers=[provider])
    res = await orch.play(body.utterance, entity=body.entity, room=body.room, vibe=body.vibe, provider_hint=body.provider_hint)
    out = {"status": "ok", "result": res}
    if key:
        await set_idempotent(key, user_id, out)
    return out

import asyncio
import hashlib
import inspect
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from app.models.common import OkResponse as CommonOkResponse

from ..deps.user import get_current_user_id

# Use unified Spotify client that reads/writes tokens via auth_store_tokens
from ..integrations.spotify.client import SpotifyAuthError, SpotifyClient
from ..models.music_state import MusicVibe, load_state, save_state

router = APIRouter(prefix="", tags=["Music"])  # rate limit applied selectively in main


# ---------------------------------------------------------------------------
# Feature flags and env
# ---------------------------------------------------------------------------

# Default provider flags (favor safer defaults in test environments)
_TEST_MODE = (
    bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_RUNNING"))
    or os.getenv("ENV", "").strip().lower() == "test"
    or os.getenv("JWT_OPTIONAL_IN_TESTS", "0").strip().lower()
    in {"1", "true", "yes", "on"}
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
MUSIC_FALLBACK_RADIO = os.getenv("MUSIC_FALLBACK_RADIO", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
EXPLICIT_DEFAULT = os.getenv("EXPLICIT_DEFAULT", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

QUIET_START = os.getenv("QUIET_HOURS_START", "22:00")
QUIET_END = os.getenv("QUIET_HOURS_END", "07:00")

ALBUM_DIR = Path(os.getenv("ALBUM_ART_DIR", "data/album_art")).resolve()
ALBUM_DIR.mkdir(parents=True, exist_ok=True)
RADIO_URL = os.getenv("FALLBACK_RADIO_URL", "")


DEFAULT_VIBES: dict[str, MusicVibe] = {
    "Calm Night": MusicVibe(name="Calm Night", energy=0.25, tempo=80, explicit=False),
    "Turn Up": MusicVibe(name="Turn Up", energy=0.9, tempo=128, explicit=False),
    "Uplift Morning": MusicVibe(
        name="Uplift Morning", energy=0.6, tempo=110, explicit=False
    ),
}


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm))


def _in_quiet_hours(now: datetime | None = None) -> bool:
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


def _filter_explicit(items: list[dict], *, allow_explicit: bool) -> list[dict]:
    """Filter out explicit items when explicit content is not allowed.

    Operates on provider-raw recommendation items.
    """
    if allow_explicit:
        return list(items)
    return [t for t in items if not bool(t.get("explicit"))]


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


# ---------------------------------------------------------------------------
# ETag helpers
# ---------------------------------------------------------------------------


def _user_namespace(user_id: str) -> str:
    test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
    return f"u:{user_id}:{test_salt}" if test_salt else f"u:{user_id}"


def _strong_etag(name: str, user_id: str, payload: Any) -> str:
    try:
        base = {
            "n": name,
            "u": _user_namespace(user_id),
            "p": payload,
            "v": 1,
        }
        raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode("utf-8")
        h = hashlib.sha256(raw).hexdigest()
        return f'"{name}:{h[:32]}"'
    except Exception:
        rnd = hashlib.sha256(os.urandom(16)).hexdigest()
        return f'"{name}:{rnd[:32]}"'


def _attach_cache_headers(response: Response, etag: str) -> None:
    try:
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, no-cache, must-revalidate"
        response.headers["Vary"] = "Authorization, Cookie"
    except Exception:
        pass


def _maybe_304(request: Request, response: Response, etag: str) -> Response | None:
    try:
        inm = request.headers.get("if-none-match") or request.headers.get(
            "If-None-Match"
        )
        if inm and inm.strip() == etag:
            _attach_cache_headers(response, etag)
            return Response(status_code=304, headers=dict(response.headers))
    except Exception:
        return None
    return None


_PAUSE_POLL_AFTER_NO_PLAY_S = int(os.getenv("MUSIC_POLL_PAUSE_AFTER_NO_PLAY_S", str(5 * 60)))
_last_play_ts: dict[str, float] = {}


def _record_play_activity(user_id: str, is_playing: bool) -> None:
    if is_playing:
        _last_play_ts[user_id] = time.time()


def _should_pause_polling(user_id: str) -> bool:
    ts = _last_play_ts.get(user_id)
    if not ts:
        return False
    return (time.time() - ts) > float(_PAUSE_POLL_AFTER_NO_PLAY_S)


async def _provider_state(user_id: str) -> dict | None:
    if not PROVIDER_SPOTIFY:
        return None
    try:
        client = SpotifyClient(user_id)
        st = await client.get_currently_playing()
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
        return await client.next_track()
    except SpotifyAuthError:
        return False
    except Exception:
        return False


async def _provider_previous(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.previous_track()
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
        return await client.get_recommendations(
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
# In-memory recommendations cache (keyed by user + seeds/params) with TTL
# ---------------------------------------------------------------------------

_RECS_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_RECS_CACHE_TTL_S: int = int(os.getenv("RECS_CACHE_TTL", "180") or 180)
# Optional TTL (seconds) for state-backed recommendations cache; 0 disables TTL (serve when present)
_RECS_STATE_TTL_S: int = int(
    os.getenv("RECS_STATE_TTL_S", os.getenv("RECS_STATE_TTL", "0")) or 0
)


def _recs_cache_key(user_id: str, seeds: list[str] | None, vibe: MusicVibe) -> tuple:
    provider = "spotify" if PROVIDER_SPOTIFY else "default"
    # Normalize seeds: lowercase, strip, dedupe, sort
    norm_seeds: list[str] = []
    if seeds:
        seen: set[str] = set()
        for s in seeds:
            if s is None:
                continue
            v = str(s).strip().lower()
            if not v or v in seen:
                continue
            seen.add(v)
            norm_seeds.append(v)
        norm_seeds.sort()
    # Stable key tuple; exclude limit so varying limits still hit cache and clamp later
    # Include a version token for future busting and pytest salt for isolation
    test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
    key = (
        user_id,
        provider,
        tuple(norm_seeds),
        # placeholder for artists/markets params to keep shape stable
        tuple(),
        "US",
        round(float(vibe.energy), 3),
        int(round(float(vibe.tempo))),
        bool(vibe.explicit),
        "v1",
        test_salt,
    )
    return key


def _recs_get_cached(key: tuple) -> list[dict] | None:
    try:
        exp_ts, items = _RECS_CACHE.get(key, (0.0, []))
        if not items:
            return None
        now_m = time.monotonic()
        if now_m < float(exp_ts):
            return items
        # expired
        _RECS_CACHE.pop(key, None)
        return None
    except Exception:
        return None


def _recs_set_cached(key: tuple, items: list[dict]) -> None:
    try:
        _RECS_CACHE[key] = (time.monotonic() + float(_RECS_CACHE_TTL_S), list(items))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class MusicCommand(BaseModel):
    command: str = Field(..., description="play|pause|next|previous|volume")
    volume: int | None = None
    device_id: str | None = None
    temporary: bool = False  # when true, store prior volume to restore later

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"command": "volume", "volume": 20, "temporary": True}
        }
    )


class VibeBody(BaseModel):
    name: str | None = None
    energy: float | None = Field(None, ge=0.0, le=1.0)
    tempo: float | None = None
    explicit: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Calm Night",
                "energy": 0.3,
                "tempo": 85,
                "explicit": False,
            }
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


async def _broadcast(topic: str, payload: dict) -> None:
    """Broadcast to WebSocket clients (legacy implementation removed)"""
    # Note: Broadcasting is now handled by music_ws.py via ws_manager
    pass


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------


async def _build_state_payload(user_id: str) -> StateResponse:
    state = load_state(user_id)

    # Ensure state is always a MusicState object, not a dict
    if isinstance(state, dict):
        logger.warning(f"load_state returned dict instead of MusicState object: {state}")
        # Convert dict back to MusicState if needed
        from ..models.music_state import MusicState, MusicVibe
        vibe_data = state.get("vibe", {})
        state = MusicState(
            vibe=MusicVibe(
                name=vibe_data.get("name", "Calm Night"),
                energy=float(vibe_data.get("energy", 0.25)),
                tempo=float(vibe_data.get("tempo", 80)),
                explicit=bool(vibe_data.get("explicit", False))
            ),
            volume=int(state.get("volume", 40)),
            device_id=state.get("device_id"),
            last_track_id=state.get("last_track_id"),
            radio_playing=bool(state.get("radio_playing", False)),
            quiet_hours=bool(state.get("quiet_hours", False)),
            explicit_allowed=bool(state.get("explicit_allowed", True))
        )

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
        images = (item.get("album") or {}).get("images") or []
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

    provider = (
        "spotify" if PROVIDER_SPOTIFY else ("radio" if MUSIC_FALLBACK_RADIO else None)
    )
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
        radio_playing=(
            state.radio_playing
            if (not PROVIDER_SPOTIFY and MUSIC_FALLBACK_RADIO)
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class OkResponse(CommonOkResponse):
    model_config = ConfigDict(title="OkResponse")


@router.post(
    "/music",
    response_model=OkResponse,
    responses={200: {"model": OkResponse}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "command": "volume",
                            "volume": 20,
                            "temporary": True,
                        }
                    }
                }
            }
        }
    },
)
async def music_command(
    body: MusicCommand, user_id: str = Depends(get_current_user_id)
):
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
        await _broadcast("music.state", (await _build_state_payload(user_id)).model_dump())
    return {"status": "ok"}


class VibeResponse(BaseModel):
    status: str = "ok"
    vibe: dict

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "vibe": {
                    "name": "Calm Night",
                    "energy": 0.3,
                    "tempo": 85,
                    "explicit": False,
                },
            }
        }
    )


@router.post(
    "/vibe",
    response_model=VibeResponse,
    responses={200: {"model": VibeResponse}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "name": "Calm Night",
                            "energy": 0.3,
                            "tempo": 85,
                            "explicit": False,
                        }
                    }
                }
            }
        }
    },
)
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
            explicit=(
                bool(body.explicit) if body.explicit is not None else vibe.explicit
            ),
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
    await _broadcast("music.state", (await _build_state_payload(user_id)).model_dump())
    return {"status": "ok", "vibe": asdict(state.vibe)}


@router.post(
    "/music/restore", response_model=OkResponse, responses={200: {"model": OkResponse}}
)
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
        await _broadcast("music.state", (await _build_state_payload(user_id)).model_dump())
    return {"status": "ok"}


@router.get("/state")
async def get_state(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    """Get music state for frontend compatibility at /v1/api/music/state"""
    return await _get_state_impl(request, response, user_id)


async def _get_state_impl(
    request: Request, response: Response, user_id: str
):
    """Actual implementation of get_state that can be called from multiple routes"""
    try:
        body = await _build_state_payload(user_id)
    except Exception as e:
        logger.error(f"Error in _build_state_payload: {e}")
        # Return a fallback response if _build_state_payload fails
        return {
            "vibe": {"name": "Default", "energy": 0.5, "tempo": 120, "explicit": False},
            "volume": 50,
            "device_id": None,
            "is_playing": False,
            "track": None,
            "quiet_hours": False,
            "explicit_allowed": True,
            "provider": None,
            "radio_url": None,
            "radio_playing": None,
        }

    try:
        # Handle both dict and StateResponse object cases
        def safe_get(key: str, default=None):
            if isinstance(body, dict):
                return body.get(key, default)
            else:
                return getattr(body, key, default)

        stable = {
            "vibe": safe_get("vibe"),
            "volume": int(safe_get("volume", 0)),
            "device_id": safe_get("device_id"),
            "is_playing": (
                bool(safe_get("is_playing"))
                if safe_get("is_playing") is not None else None
            ),
            "track_id": (safe_get("track") or {}).get("id") if safe_get("track") else None,
            "quiet_hours": bool(safe_get("quiet_hours", False)),
            "explicit_allowed": bool(safe_get("explicit_allowed", False)),
            "provider": safe_get("provider"),
            "radio_url": safe_get("radio_url"),
            "radio_playing": safe_get("radio_playing"),
        }
        etag = _strong_etag("music.state", user_id, stable)
        r304 = _maybe_304(request, response, etag)
        if r304 is not None:
            return r304  # type: ignore[return-value]
        _attach_cache_headers(response, etag)
    except Exception as e:
        logger.error(f"Error in _get_state_impl processing: {e}")
        pass
    return body


# Add state endpoint to root router for frontend compatibility
@root_router.get("/state")
async def get_state_root(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    """Get music state for frontend compatibility at /v1/state"""
    return await _get_state_impl(request, response, user_id)


@router.get("/queue")
async def get_queue(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    state = load_state(user_id)
    if not PROVIDER_SPOTIFY:
        asyncio.create_task(_broadcast("music.queue.updated", {"count": 0}))
        body = {"current": None, "up_next": [], "skip_count": state.skip_count}
        try:
            etag = _strong_etag(
                "music.queue",
                user_id,
                {"current": None, "ids": [], "skip": int(state.skip_count)},
            )
            r304 = _maybe_304(request, response, etag)
            if r304 is not None:
                return r304  # type: ignore[return-value]
            _attach_cache_headers(response, etag)
        except Exception:
            pass
        return body
    _qres = _provider_queue(user_id)
    current, queue = (await _qres) if inspect.isawaitable(_qres) else _qres
    # Broadcast queue update for listeners
    asyncio.create_task(_broadcast("music.queue.updated", {"count": len(queue)}))

    # Map to minimal shape
    async def _map(item: dict | None) -> dict | None:
        if not item:
            return None
        tid = item.get("id") if item else None
        images = (item.get("album") or {}).get("images") or []
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
    body = {
        "current": mapped_current,
        "up_next": mapped_queue,
        "skip_count": state.skip_count,
    }
    try:
        stable = {
            "cur": (mapped_current or {}).get("id") if mapped_current else None,
            "ids": [t.get("id") for t in mapped_queue if isinstance(t, dict)],
            "skip": int(state.skip_count),
        }
        etag = _strong_etag("music.queue", user_id, stable)
        r304 = _maybe_304(request, response, etag)
        if r304 is not None:
            return r304  # type: ignore[return-value]
        _attach_cache_headers(response, etag)
    except Exception:
        pass
    return body


@router.get("/recommendations")
async def get_recommendations(
    request: Request,
    response: Response,
    limit: int = 6,
    user_id: str = Depends(get_current_user_id),
):
    state = load_state(user_id)
    # Clamp requested limit to [1, 10]
    try:
        raw_limit = int(limit or 10)
    except (TypeError, ValueError):
        raw_limit = 10
    clamp = max(1, min(10, raw_limit))

    # Provider-enabled flows: prefer fresh provider data (so tests that monkeypatch
    # the provider see their results), falling back to in-memory cache.
    tracks_raw: list[dict] = []
    seeds: list[str] | None = [state.last_track_id] if state.last_track_id else None
    if PROVIDER_SPOTIFY:
        cache_key = _recs_cache_key(user_id, seeds, state.vibe)
        cached = _recs_get_cached(cache_key)
        if cached:
            tracks_raw = list(cached)
        else:
            # Ask provider for up to the clamped limit; provider may return more
            _rres = _provider_recommendations(
                user_id,
                seed_tracks=seeds,
                vibe=state.vibe,
                limit=clamp,
            )
            tracks_raw = await _rres if inspect.isawaitable(_rres) else _rres
            # Cache provider-raw items so we can re-slice per request
            _recs_set_cached(cache_key, tracks_raw)
    else:
        # Provider disabled: allow serving from state-backed cache first
        if state.last_recommendations:
            try:
                if _RECS_STATE_TTL_S <= 0:
                    return {"recommendations": state.last_recommendations[:clamp]}
                if state.recs_cached_at is not None and (
                    time.time() - float(state.recs_cached_at) < _RECS_STATE_TTL_S
                ):
                    return {"recommendations": state.last_recommendations[:clamp]}
            except Exception:
                return {"recommendations": state.last_recommendations[:clamp]}

    # If provider returned nothing but we have state-backed cache, serve it
    if not tracks_raw and state.last_recommendations:
        try:
            if _RECS_STATE_TTL_S <= 0:
                return {"recommendations": state.last_recommendations[:clamp]}
            if state.recs_cached_at is not None and (
                time.time() - float(state.recs_cached_at) < _RECS_STATE_TTL_S
            ):
                return {"recommendations": state.last_recommendations[:clamp]}
        except Exception:
            return {"recommendations": state.last_recommendations[:clamp]}

    # Apply explicit filter, then clamp to requested limit, then map to response shape
    allowed = _explicit_allowed(state.vibe)
    filtered = _filter_explicit(tracks_raw, allow_explicit=allowed)
    filtered = filtered[:clamp]
    out: list[dict] = []
    for t in filtered:
        tid = t.get("id")
        images = (t.get("album") or {}).get("images") or []
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

    # Persist and cache for future requests (state and in-memory)
    state.last_recommendations = out
    state.recs_cached_at = time.time()
    save_state(user_id, state)
    # In-memory cache already stores provider-raw; do not overwrite with mapped output
    body = {"recommendations": out}
    try:
        stable = {
            "ids": [t.get("id") for t in out if isinstance(t, dict)],
            "limit": clamp,
        }
        etag = _strong_etag("music.recs", user_id, stable)
        r304 = _maybe_304(request, response, etag)
        if r304 is not None:
            return r304  # type: ignore[return-value]
        _attach_cache_headers(response, etag)
    except Exception:
        pass
    return body


class DeviceBody(BaseModel):
    device_id: str

    model_config = ConfigDict(json_schema_extra={"example": {"device_id": "abcdef123"}})


@router.get("/music/devices")
async def list_devices(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    logger.info("🎵 MUSIC DEVICES: Request started", extra={
        "meta": {
            "user_id": user_id,
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "provider_spotify_enabled": PROVIDER_SPOTIFY
        }
    })

    if not PROVIDER_SPOTIFY:
        logger.warning("🎵 MUSIC DEVICES: Spotify provider not enabled", extra={
            "meta": {"user_id": user_id}
        })
        body = {"devices": []}
        try:
            etag = _strong_etag("music.devices", user_id, {"ids": []})
            r304 = _maybe_304(request, response, etag)
            if r304 is not None:
                logger.info("🎵 MUSIC DEVICES: Returning 304 Not Modified", extra={
                    "meta": {"user_id": user_id, "etag": etag}
                })
                return r304  # type: ignore[return-value]
            _attach_cache_headers(response, etag)
        except Exception as e:
            logger.warning("🎵 MUSIC DEVICES: Cache header error", extra={
                "meta": {"user_id": user_id, "error": str(e)}
            })
        logger.info("🎵 MUSIC DEVICES: Returning empty devices (Spotify disabled)", extra={
            "meta": {"user_id": user_id}
        })
        return body

    try:
        logger.info("🎵 MUSIC DEVICES: Creating Spotify client", extra={
            "meta": {"user_id": user_id}
        })
        client = SpotifyClient(user_id)
        logger.info("🎵 MUSIC DEVICES: Calling get_devices()", extra={
            "meta": {"user_id": user_id}
        })
        devices = await client.get_devices()
        logger.info("🎵 MUSIC DEVICES: get_devices() completed", extra={
            "meta": {
                "user_id": user_id,
                "device_count": len(devices) if devices else 0,
                "devices": devices
            }
        })
    except SpotifyAuthError as e:
        logger.warning("🎵 MUSIC DEVICES: Spotify auth error", extra={
            "meta": {"user_id": user_id, "error": str(e)}
        })
        devices = []
    except Exception as e:
        logger.error("🎵 MUSIC DEVICES: Unexpected error getting devices", extra={
            "meta": {"user_id": user_id, "error": str(e), "error_type": type(e).__name__}
        })
        devices = []

    body = {"devices": devices}
    logger.info("🎵 MUSIC DEVICES: Preparing response", extra={
        "meta": {
            "user_id": user_id,
            "device_count": len(devices) if devices else 0,
            "response_body": body
        }
    })

    try:
        stable = {"ids": [d.get("id") for d in devices if isinstance(d, dict)]}
        etag = _strong_etag("music.devices", user_id, stable)
        r304 = _maybe_304(request, response, etag)
        if r304 is not None:
            logger.info("🎵 MUSIC DEVICES: Returning 304 Not Modified (with data)", extra={
                "meta": {"user_id": user_id, "etag": etag}
            })
            return r304  # type: ignore[return-value]
        _attach_cache_headers(response, etag)
        logger.info("🎵 MUSIC DEVICES: Attached cache headers", extra={
            "meta": {"user_id": user_id, "etag": etag}
        })
    except Exception as e:
        logger.warning("🎵 MUSIC DEVICES: Cache header error (with data)", extra={
            "meta": {"user_id": user_id, "error": str(e)}
        })

    logger.info("🎵 MUSIC DEVICES: Returning devices", extra={
        "meta": {
            "user_id": user_id,
            "device_count": len(devices) if devices else 0,
            "final_response": body
        }
    })
    return body


@router.post(
    "/music/device", response_model=OkResponse, responses={200: {"model": OkResponse}}
)
async def set_device(body: DeviceBody, user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    state.device_id = body.device_id
    save_state(user_id, state)
    if PROVIDER_SPOTIFY:
        try:
            client = SpotifyClient(user_id)
            await client.transfer_playback(body.device_id, play=True)
        except Exception:
            # Non-fatal in tests or when auth not configured
            pass
    await _broadcast("music.state", (await _build_state_payload(user_id)).model_dump())
    return {"status": "ok"}


# Export the routers for use in main.py
__all__ = ["router", "root_router"]

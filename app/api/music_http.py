from __future__ import annotations

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

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.music import PROVIDER_SPOTIFY
from app.deps.scopes import require_scope
from app.deps.user import get_current_user_id
from app.integrations.spotify.client import SpotifyAuthError, SpotifyClient
from app.models.common import OkResponse as CommonOkResponse
from app.models.music_state import MusicVibe
from app.models.music_state import load_state as load_state_memory
from app.models.music_state import save_state as save_state_memory
from app.music.orchestrator import MusicOrchestrator
from app.music.providers.spotify_provider import SpotifyProvider
from app.music.store import get_music_session, load_music_state, save_music_state

router = APIRouter(prefix="/music", tags=["Music"])  # mounted under /v1
logger = logging.getLogger(__name__)


# ============================================================================
# MUSIC STATE PERSISTENCE WRAPPERS
# ============================================================================


async def load_state(user_id: str):
    """Load music state, preferring database but falling back to memory."""
    try:
        # Try database first
        db_state = await load_music_state(user_id)
        if db_state:
            # Convert dict back to MusicState object
            from app.models.music_state import MusicState

            vibe_data = db_state.get("vibe", {})
            state = MusicState(
                vibe=MusicVibe(
                    name=vibe_data.get("name", "Calm Night"),
                    energy=float(vibe_data.get("energy", 0.25)),
                    tempo=float(vibe_data.get("tempo", 80)),
                    explicit=bool(vibe_data.get("explicit", False)),
                ),
                volume=int(db_state.get("volume", 25)),
                device_id=db_state.get("device_id"),
                last_track_id=db_state.get("last_track_id"),
                last_recommendations=db_state.get("last_recommendations"),
                recs_cached_at=db_state.get("recs_cached_at"),
                duck_from=db_state.get("duck_from"),
                quiet_hours=bool(db_state.get("quiet_hours", False)),
                explicit_allowed=bool(db_state.get("explicit_allowed", True)),
                radio_playing=bool(db_state.get("radio_playing", True)),
                skip_count=int(db_state.get("skip_count", 0)),
            )
            return state
    except Exception:
        # Fall back to in-memory if database fails
        pass

    # Fallback to in-memory state
    return load_state_memory(user_id)


async def save_state(user_id: str, state):
    """Save music state to database and memory."""
    try:
        # Try to save to database first
        session_id = await get_music_session(user_id)
        if session_id:
            # Convert MusicState to dict for database
            state_dict = {
                "vibe": {
                    "name": state.vibe.name,
                    "energy": state.vibe.energy,
                    "tempo": state.vibe.tempo,
                    "explicit": state.vibe.explicit,
                },
                "volume": state.volume,
                "device_id": state.device_id,
                "last_track_id": state.last_track_id,
                "last_recommendations": state.last_recommendations,
                "recs_cached_at": state.recs_cached_at,
                "duck_from": state.duck_from,
                "quiet_hours": state.quiet_hours,
                "explicit_allowed": state.explicit_allowed,
                "radio_playing": state.radio_playing,
                "skip_count": state.skip_count,
            }
            await save_music_state(user_id, session_id, state_dict)
            return
    except Exception:
        # Fall back to in-memory if database fails
        pass

    # Fallback to in-memory state
    save_state_memory(user_id, state)


# ---------------------------------------------------------------------------
# Feature flags and env
# ---------------------------------------------------------------------------


def is_test_mode() -> bool:
    """Evaluate test mode dynamically at runtime so tests can set env after import."""
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("PYTEST_RUNNING")
        or os.getenv("TEST_MODE", "").strip() == "1"
        or os.getenv("ENV", "").strip().lower() == "test"
        or os.getenv("JWT_OPTIONAL_IN_TESTS", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )


def is_provider_spotify() -> bool:
    """Return whether Spotify provider should be used for the current runtime.

    This checks test mode dynamically and the PROVIDER_SPOTIFY env var.
    """
    if is_test_mode():
        return False
    return os.getenv("PROVIDER_SPOTIFY", "true").strip().lower() in {
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
        import anyio
        import httpx

        async with httpx.AsyncClient(timeout=10) as s:
            r = await s.get(url)
            if r.status_code == 200 and r.content:
                await anyio.to_thread.run_sync(dest.write_bytes, r.content)
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
        base = {"n": name, "u": _user_namespace(user_id), "p": payload, "v": 1}
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


_PAUSE_POLL_AFTER_NO_PLAY_S = int(
    os.getenv("MUSIC_POLL_PAUSE_AFTER_NO_PLAY_S", str(5 * 60))
)
MARKET = os.getenv("SPOTIFY_MARKET", "US")
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
    if not is_provider_spotify():
        return None
    try:
        if _should_pause_polling(user_id):
            return None
        client = SpotifyClient(user_id)
        st = await client.get_currently_playing()
        return st
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return None
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
        return None


async def _provider_queue(user_id: str) -> tuple[dict | None, list[dict]]:
    if not is_provider_spotify():
        return None, []
    try:
        client = SpotifyClient(user_id)
        return await client.get_queue()
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return None, []
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
        return None, []


async def _provider_play(user_id: str, uris: list[str] | None = None) -> bool:
    if not is_provider_spotify():
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.play(uris)
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return False
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
        return False


def _mk_orchestrator(user_id: str) -> MusicOrchestrator | None:
    """Construct a simple orchestrator with the Spotify provider when enabled.

    Falls back to None when provider is disabled to preserve existing radio flow.
    """
    if not is_provider_spotify():
        return None
    try:
        sp = SpotifyProvider(user_id)
        return MusicOrchestrator([sp])
    except Exception:
        return None


async def _provider_pause(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.pause()
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return False
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
        return False


async def _provider_next(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.next_track()
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return False
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
        return False


async def _provider_previous(user_id: str) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.previous_track()
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return False
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
        return False


async def _provider_set_volume(user_id: str, level: int) -> bool:
    if not PROVIDER_SPOTIFY:
        return False
    try:
        client = SpotifyClient(user_id)
        return await client.set_volume(level)
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return False
    except Exception as e:
        logger.warning("spotify.error", extra={"user_id": user_id, "err": str(e)})
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


_RECS_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_RECS_CACHE_TTL_S: int = int(os.getenv("RECS_CACHE_TTL", "180") or 180)
_RECS_STATE_TTL_S: int = int(
    os.getenv("RECS_STATE_TTL_S", os.getenv("RECS_STATE_TTL", "0")) or 0
)


def _recs_cache_key(user_id: str, seeds: list[str] | None, vibe: MusicVibe) -> tuple:
    provider = "spotify" if is_provider_spotify() else "default"
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
    test_salt = os.getenv("PYTEST_CURRENT_TEST") or ""
    key = (
        user_id,
        provider,
        tuple(norm_seeds),
        tuple(),
        MARKET,
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
        _RECS_CACHE.pop(key, None)
        return None
    except Exception:
        return None


def _recs_set_cached(key: tuple, items: list[dict]) -> None:
    try:
        _RECS_CACHE[key] = (time.monotonic() + float(_RECS_CACHE_TTL_S), list(items))
    except Exception:
        pass


class MusicCommand(BaseModel):
    command: str = Field(..., description="play|pause|next|previous|volume")
    volume: int | None = None
    device_id: str | None = None
    temporary: bool = False

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


_ws_clients_placeholder: set[Any] = set()  # maintained by music_ws


async def _build_state_payload(user_id: str) -> StateResponse:
    state = load_state(user_id)
    quiet = _in_quiet_hours()
    sp = None
    if is_provider_spotify():
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
        art_url = next(
            (
                img.get("url")
                for img in images
                if isinstance(img, dict) and img.get("url")
            ),
            None,
        )
        if art_url and track_id:
            _cached = _ensure_album_cached(art_url, track_id)
            cached = await _cached if inspect.isawaitable(_cached) else _cached
        else:
            cached = None
        track = {
            "id": track_id,
            "name": item.get("name"),
            "artists": ", ".join([a.get("name", "") for a in item.get("artists", [])]),
            "art_url": cached or art_url,
            "duration_ms": item.get("duration_ms"),
        }
        progress_ms = sp.get("progress_ms")
        is_playing = sp.get("is_playing")
    elif MUSIC_FALLBACK_RADIO and not is_provider_spotify():
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
        "spotify"
        if is_provider_spotify()
        else ("radio" if MUSIC_FALLBACK_RADIO else None)
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
            if (not is_provider_spotify() and MUSIC_FALLBACK_RADIO)
            else None
        ),
    )


class OkResponse(CommonOkResponse):
    model_config = ConfigDict(title="OkResponse")


@router.get(
    "/music",
    response_model=OkResponse,
    responses={200: {"model": OkResponse}},
)
async def get_music():
    """Simple music surface endpoint that returns ok status."""
    return {"status": "ok"}


@router.post(
    "/music",
    response_model=OkResponse,
    responses={200: {"model": OkResponse}},
)
async def music_command(
    body: MusicCommand,
    user_id: str = Depends(get_current_user_id),
    _=Depends(require_scope("music:control")),
):
    state = load_state(user_id)
    quiet = _in_quiet_hours()
    cap = _volume_cap_for(state.vibe, quiet)
    changed = False

    if body.command == "play":
        if not is_provider_spotify() and MUSIC_FALLBACK_RADIO:
            state.radio_playing = True
            changed = True
        else:
            orch = _mk_orchestrator(user_id)
            if orch:
                await orch.resume()
            else:
                await _provider_play(user_id)
        _record_play_activity(user_id, True)
    elif body.command == "pause":
        if not is_provider_spotify() and MUSIC_FALLBACK_RADIO:
            state.radio_playing = False
            changed = True
        else:
            orch = _mk_orchestrator(user_id)
            if orch:
                await orch.pause()
            else:
                await _provider_pause(user_id)
        _record_play_activity(user_id, False)
    elif body.command == "next":
        if is_provider_spotify():
            orch = _mk_orchestrator(user_id)
            if orch:
                await orch.next()
            else:
                await _provider_next(user_id)
        state.skip_count = (state.skip_count or 0) + 1
        changed = True
    elif body.command == "previous":
        if is_provider_spotify():
            orch = _mk_orchestrator(user_id)
            if orch:
                await orch.previous()
            else:
                await _provider_previous(user_id)
    elif body.command == "volume":
        if body.volume is None:
            raise HTTPException(status_code=400, detail="missing_volume")
        new_level = max(0, min(cap, int(body.volume)))
        if body.temporary and getattr(state, "duck_from", None) is None:
            state.duck_from = state.volume
        state.volume = new_level
        changed = True
        if is_provider_spotify():
            orch = _mk_orchestrator(user_id)
            if orch:
                await orch.set_volume(new_level)
            else:
                await _provider_set_volume(user_id, new_level)
    else:
        raise HTTPException(status_code=400, detail="unknown_command")

    if changed:
        state.quiet_hours = quiet
        state.explicit_allowed = _explicit_allowed(state.vibe)
        save_state(user_id, state)
    return {"status": "ok"}


class VibeResponse(BaseModel):
    status: str = "ok"
    vibe: dict

    model_config = ConfigDict(
        title="VibeResponse", json_schema_extra={"title": "VibeResponse"}
    )


@router.post(
    "/vibe", response_model=VibeResponse, responses={200: {"model": VibeResponse}}
)
async def set_vibe(
    body: VibeBody,
    user_id: str = Depends(get_current_user_id),
    _=Depends(require_scope("music:control")),
):
    state = load_state(user_id)
    if body.name and body.name in DEFAULT_VIBES:
        state.vibe = DEFAULT_VIBES[body.name]
    else:
        vibe = state.vibe
        state.vibe = MusicVibe(
            name=body.name or vibe.name,
            energy=float(body.energy) if body.energy is not None else vibe.energy,
            tempo=float(body.tempo) if body.tempo is not None else vibe.tempo,
            explicit=(
                bool(body.explicit) if body.explicit is not None else vibe.explicit
            ),
        )
    quiet = _in_quiet_hours()
    cap = _volume_cap_for(state.vibe, quiet)
    if state.volume > cap:
        state.volume = cap
        await _provider_set_volume(user_id, cap)
    state.quiet_hours = quiet
    state.explicit_allowed = _explicit_allowed(state.vibe)
    save_state(user_id, state)
    return {"status": "ok", "vibe": asdict(state.vibe)}


@router.get("/state", response_model=StateResponse, deprecated=True)
async def music_state(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    payload = await _build_state_payload(user_id)

    def _state_fingerprint(state) -> dict:
        # Handle both StateResponse objects and dict inputs
        if isinstance(state, dict):
            vibe = state.get("vibe") or {}
            track = state.get("track") or {}
            return {
                "t": track.get("id"),
                "p": bool(state.get("is_playing", False)),
                "v": int(state.get("volume", 0)),
                "d": state.get("device_id"),
                "vb": round(float(vibe.get("energy", 0) or 0), 2),
                "vt": int(float(vibe.get("tempo", 0) or 0)),
                "e": bool(vibe.get("explicit", False)),
            }
        else:
            # Handle StateResponse object
            vibe = state.vibe or {}
            return {
                "t": (state.track or {}).get("id"),
                "p": bool(state.is_playing),
                "v": int(state.volume),
                "d": state.device_id,
                "vb": round(float(vibe.get("energy", 0) or 0), 2),
                "vt": int(float(vibe.get("tempo", 0) or 0)),
                "e": bool(vibe.get("explicit", False)),
            }

    finger = _state_fingerprint(payload.model_dump())
    etag = _strong_etag("state", user_id, finger)
    maybe = _maybe_304(request, response, etag)
    if maybe is not None:
        return maybe
    _attach_cache_headers(response, etag)
    return payload


@router.post(
    "/restore_volume", response_model=OkResponse, responses={200: {"model": OkResponse}}
)
async def restore_volume(user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    if getattr(state, "duck_from", None) is not None:
        restored = int(state.duck_from)
        state.duck_from = None
        quiet = _in_quiet_hours()
        cap = _volume_cap_for(state.vibe, quiet)
        level = max(0, min(cap, restored))
        state.volume = level
        await _provider_set_volume(user_id, level)
        save_state(user_id, state)
    return {"status": "ok"}


@router.get("/queue")
async def get_queue(user_id: str = Depends(get_current_user_id)):
    _, q = await _provider_queue(user_id)
    return {"up_next": q}


@router.get("/recommendations")
async def recommendations(user_id: str = Depends(get_current_user_id)):
    state = load_state(user_id)
    vibe = state.vibe
    seeds = [state.last_track_id] if getattr(state, "last_track_id", None) else None
    key = _recs_cache_key(user_id, seeds, vibe)
    cached = _recs_get_cached(key)
    if cached is not None:
        return {"items": cached}
    if not seeds:
        return {"items": [], "hint": "no_seed_track_yet"}
    # Prefer orchestrator for consistency across providers
    orch = _mk_orchestrator(user_id)
    if orch:
        try:
            items = await orch.recommend_more_like(seed_track_id=seeds[0], limit=20)
        except Exception:
            items = []
    else:
        items = await _provider_recommendations(
            user_id, seed_tracks=seeds, vibe=vibe, limit=20
        )
    _recs_set_cached(key, items)
    return {"items": items}


@router.get("/music/devices")
async def list_devices(user_id: str = Depends(get_current_user_id)):
    orch = _mk_orchestrator(user_id)
    if orch:
        try:
            items = await orch.list_devices()
            return {"items": items}
        except Exception:
            return {"items": []}
    # Fallback to legacy direct client for back-compat
    if not is_provider_spotify():
        return {"items": []}
    try:
        client = SpotifyClient(user_id)
        res = await client.get_devices()
        return {"items": res or []}
    except SpotifyAuthError:
        return {"items": []}


class TransferBody(BaseModel):
    device_id: str | None = None


@router.put(
    "/music/device",
    response_model=CommonOkResponse,
    responses={
        200: {"model": CommonOkResponse},
        400: {"description": "Missing device_id"},
    },
)
async def put_music_device(body: TransferBody):
    """Simple PUT handler for music device endpoint that validates device_id presence."""
    device_id = (body.device_id or "").strip()
    if not device_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="missing device_id")
    return {"status": "ok"}


@router.post(
    "/music/device",
    response_model=CommonOkResponse,
    responses={200: {"model": CommonOkResponse}},
)
async def transfer_playback_device(
    body: TransferBody,
    user_id: str = Depends(get_current_user_id),
    _=Depends(require_scope("music:control")),
):
    device_id = (body.device_id or "").strip() or None
    if not device_id:
        return {"status": "ok"}
    orch = _mk_orchestrator(user_id)
    if orch:
        try:
            await orch.transfer_playback(device_id, force_play=True)
        except Exception:
            pass
        return {"status": "ok"}
    if not PROVIDER_SPOTIFY:
        return {"status": "ok"}
    try:
        client = SpotifyClient(user_id)
        await client.transfer_playback(device_id)
        return {"status": "ok"}
    except SpotifyAuthError:
        logger.warning("spotify.auth_error", extra={"user_id": user_id})
        return {"status": "ok"}


# Legacy redirect router for backward compatibility
# This should be mounted at /v1 level (not under /music)
redirect_router = APIRouter()


@redirect_router.get("/legacy/state", include_in_schema=True, deprecated=True)
async def legacy_music_state_redirect():
    """Redirect legacy /v1/legacy/state calls to new /v1/state endpoint."""
    return RedirectResponse(url="/v1/state", status_code=307)


__all__ = ["router", "redirect_router", "_build_state_payload"]

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.deps.user import get_current_user_id
from app.memory.profile_store import profile_store
from app.metrics import TV_MUSIC_PLAY_COUNT

router = APIRouter(tags=["TV"])  # intentionally no auth deps for device-trusted kiosk


def _list_images(dir_path: Path) -> list[str]:
    try:
        files = [
            p.name
            for p in sorted(dir_path.iterdir())
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}
        ]
        return files
    except Exception:
        return []


def _estimate_brightness_and_smile(img_path: Path) -> tuple[float, bool]:
    try:
        from PIL import Image, ImageStat  # type: ignore

        # Brightness via grayscale mean
        with Image.open(img_path) as im:
            im = im.convert("L")
            stat = ImageStat.Stat(im)
            brightness = float(stat.mean[0] if stat.mean else 0.0)
        # Very naive "smile" heuristic: filenames containing happy keywords
        name = img_path.name.lower()
        smiling = any(w in name for w in ("smile", "happy", "grin"))
        return brightness, smiling
    except Exception:
        return 0.0, False


def _is_quiet_hours_active() -> bool:
    try:
        from datetime import datetime
        from datetime import time as dt_time

        q_enabled = os.getenv("QUIET_HOURS", "0").lower() in {"1", "true", "yes", "on"}
        if not q_enabled:
            return False
        start_s = os.getenv("QUIET_HOURS_START", "22:00")
        end_s = os.getenv("QUIET_HOURS_END", "07:00")
        hh, mm = (start_s or "0:0").split(":", 1)
        start_t = dt_time(int(hh), int(mm))
        hh2, mm2 = (end_s or "0:0").split(":", 1)
        end_t = dt_time(int(hh2), int(mm2))
        now = datetime.now().time()
        if start_t <= end_t:
            return start_t <= now <= end_t
        return now >= start_t or now <= end_t
    except Exception:
        return False


@router.get("/tv/photos")
async def tv_photos():
    """Return slideshow folder and items.

    Configure via:
      - TV_PHOTOS_DIR: absolute or relative path to image folder (default: data/shared_photos)
      - TV_PHOTOS_URL_BASE: URL base the TV app uses to fetch files (default: /shared_photos)
    """
    dir_str = os.getenv("TV_PHOTOS_DIR", "data/shared_photos")
    base_url = os.getenv("TV_PHOTOS_URL_BASE", "/shared_photos")
    dir_path = Path(dir_str)
    items = _list_images(dir_path)
    # Photo safety filter during quiet hours: prefer bright/smiling images
    if _is_quiet_hours_active():
        min_brightness = float(os.getenv("PHOTO_MIN_BRIGHTNESS_NIGHT", "60") or 60)
        safe: list[str] = []
        for name in items:
            b, smile = _estimate_brightness_and_smile(dir_path / name)
            if b >= min_brightness or smile:
                safe.append(name)
        # If nothing passes, fall back to the original list to avoid emptiness
        items = safe or items
    return {"folder": base_url, "items": items}


_FAV_FILE = Path(os.getenv("PHOTO_FAVORITES_STORE", "data/photo_favorites.json"))


class TvOkResponse(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(
        title="TvOkResponse",
        json_schema_extra={"example": {"status": "ok"}},
    )


@router.post(
    "/tv/photos/favorite",
    response_model=TvOkResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/TvOkResponse"}
                }
            }
        }
    },
)
async def tv_photos_favorite(name: str, user_id: str = Depends(get_current_user_id)):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    try:
        _FAV_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: list[str] = []
        if _FAV_FILE.exists():
            try:
                raw = json.loads(_FAV_FILE.read_text(encoding="utf-8") or "[]")
                if isinstance(raw, list):
                    data = [str(x) for x in raw]
            except Exception:
                data = []
        if name not in data:
            data.append(name)
        _FAV_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=500, detail="persist_failed")


@router.get("/tv/weather")
async def tv_weather():
    """Return a minimal weather payload.

    In production, wire to a weather provider; here we rely on environment overrides
    for deterministic output during tests/dev.
    """
    city = os.getenv("TV_CITY", os.getenv("CITY", ""))
    # Deterministic defaults with optional overrides
    now_temp = os.getenv("TV_WEATHER_NOW_F")
    try:
        now_temp_f = float(now_temp) if now_temp is not None else 72.0
    except ValueError:
        now_temp_f = 72.0
    today_hi = int(os.getenv("TV_WEATHER_TODAY_HI", "74") or 74)
    today_lo = int(os.getenv("TV_WEATHER_TODAY_LO", "60") or 60)
    tomorrow_hi = int(os.getenv("TV_WEATHER_TOM_HI", "73") or 73)
    tomorrow_lo = int(os.getenv("TV_WEATHER_TOM_LO", "59") or 59)
    desc = os.getenv("TV_WEATHER_DESC", "Sunny")
    sentence = os.getenv(
        "TV_WEATHER_SENTENCE", f"It's {int(round(now_temp_f))}° and {desc.lower()}."
    )
    return {
        "city": city,
        "now": {"temp": now_temp_f, "desc": desc, "sentence": sentence},
        "today": {"high": today_hi, "low": today_lo},
        "tomorrow": {"high": tomorrow_hi, "low": tomorrow_lo},
    }


@router.post("/tv/alert", responses={200: {"model": TvOkResponse}})
async def tv_alert(
    kind: str = "help",
    note: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """Escalation hook from TV to caregiver channel.

    This is a thin wrapper; in V1.1 we can fan-out to SMS/voice/webhook.
    """
    try:
        # Fan-out over WS so caregivers can see real-time alerts
        try:
            from app.api.care_ws import broadcast_resident

            resident_id = os.getenv("TV_RESIDENT_ID", "me")
            await broadcast_resident(
                resident_id, "alert.created", {"kind": kind, "note": note}
            )
        except Exception:
            pass
        return {"status": "accepted", "kind": kind, "note": note}
    except Exception:
        raise HTTPException(status_code=500, detail="alert_failed")


@router.get("/tv/tips")
async def tv_ambient_tips():
    """Ambient tips via lightweight local RAG-style mashup.

    Example: "It's 72°F and cloudy; lo-fi playlist queued."
    """
    # Weather from existing endpoint (or env defaults)
    try:
        w = await tv_weather()
    except Exception:
        w = {"now": {"temp": 72, "desc": "Cloudy"}}
    temp = int(round(float(w.get("now", {}).get("temp") or 72)))
    desc = str(w.get("now", {}).get("desc") or "cloudy").lower()
    # Very small prompt-free heuristic for vibe
    vibe = (
        "lo-fi"
        if "cloud" in desc or temp < 68
        else ("chill" if temp < 78 else "upbeat")
    )
    tip = f"It's {temp}°F and {desc}; {vibe} playlist queued."
    return {"status": "ok", "tip": tip}


@router.post(
    "/tv/music/play",
    response_model=TvOkResponse,
    responses={200: {"model": TvOkResponse}},
)
async def tv_music_play(preset: str, user_id: str = Depends(get_current_user_id)):
    """Start playing a local preset playlist (placeholder)."""
    import logging

    logger = logging.getLogger(__name__)

    # Enhanced logging with user_id, route, and auth_state
    logger.info(
        "🎵 TV MUSIC PLAY: Request started",
        extra={
            "user_id": user_id,
            "route": "/v1/tv/music/play",
            "auth_state": (
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
            "meta": {"preset": preset},
        },
    )

    name = (preset or "").strip()
    if not name:
        logger.warning(
            "🎵 TV MUSIC PLAY: Empty preset",
            extra={
                "user_id": user_id,
                "route": "/v1/tv/music/play",
                "auth_state": (
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
            },
        )

        # Track metrics for validation errors
        try:
            TV_MUSIC_PLAY_COUNT.labels(status="400").inc()
        except Exception:
            pass

        raise HTTPException(status_code=400, detail="empty_preset")

    # TODO: integrate with local player (mpv/afplay) or Spotify/Apple connectors

    # Track metrics for successful requests
    try:
        TV_MUSIC_PLAY_COUNT.labels(status="200").inc()
    except Exception:
        pass

    logger.info(
        "🎵 TV MUSIC PLAY: Request successful",
        extra={
            "user_id": user_id,
            "route": "/v1/tv/music/play",
            "auth_state": (
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
            "meta": {"preset": preset, "playing": name},
        },
    )

    return {"status": "ok", "playing": name}


@router.get("/tv/prefs")
async def tv_get_prefs(user_id: str = Depends(get_current_user_id)):
    prof = profile_store.get(user_id)
    return {
        "name": prof.get("name"),
        "speech_rate": prof.get("speech_rate"),
        "input_mode": prof.get("input_mode"),
        "font_scale": prof.get("font_scale"),
        "wake_word_enabled": prof.get("wake_word_enabled", False),
        "address_style": prof.get("address_style"),
    }


@router.post(
    "/tv/prefs",
    response_model=TvOkResponse,
    responses={200: {"model": TvOkResponse}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "speech_rate": {"type": "string"},
                            "input_mode": {"type": "string"},
                            "font_scale": {"type": "string"},
                            "wake_word_enabled": {"type": "boolean"},
                            "address_style": {"type": "string"},
                        },
                        "example": {"name": "Ava", "speech_rate": "normal"},
                    }
                }
            }
        }
    },
)
async def tv_set_prefs(
    name: str | None = None,
    speech_rate: str | None = None,
    input_mode: str | None = None,
    font_scale: str | None = None,
    wake_word_enabled: bool | None = None,
    address_style: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    data = {}
    if name is not None:
        data["name"] = name
    if speech_rate is not None:
        data["speech_rate"] = speech_rate
    if input_mode is not None:
        data["input_mode"] = input_mode
    if font_scale is not None:
        data["font_scale"] = font_scale
    if wake_word_enabled is not None:
        data["wake_word_enabled"] = bool(wake_word_enabled)
    if address_style is not None:
        data["address_style"] = address_style
    if data:
        profile_store.update(user_id, data)
    return {"status": "ok"}


class Stage2Body(BaseModel):
    tiles: list[str] | None = None
    rhythm: str | None = None
    helpfulness: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tiles": ["calendar", "music"],
                "rhythm": "morning",
                "helpfulness": "high",
            }
        }
    )


@router.post(
    "/tv/stage2",
    response_model=TvOkResponse,
    responses={200: {"model": TvOkResponse}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Stage2Body"}
                }
            }
        }
    },
)
async def tv_stage2(
    body: Stage2Body,
    user_id: str = Depends(get_current_user_id),
):
    data = {}
    if body.tiles is not None:
        data["preferences_tiles"] = body.tiles
    if body.rhythm is not None:
        data["daily_rhythm"] = body.rhythm
    if body.helpfulness is not None:
        data["helpfulness"] = body.helpfulness
    if data:
        profile_store.update(user_id, data)
    return {"status": "ok"}


# -----------------------------
# TV Config per-resident
# -----------------------------


from app.models.tv import QuietHours, TvConfig, TvConfigResponse, TVConfigUpdate


@router.get(
    "/tv/config",
    response_model=TvConfigResponse,
    responses={200: {"model": TvConfigResponse}},
)
async def tv_get_config(resident_id: str):
    from app.care_store import get_tv_config

    rec = await get_tv_config(resident_id)
    if not rec:
        # Default config when none saved
        cfg = TvConfig()
        return {"status": "ok", "config": cfg.model_dump()}
    cfg = TvConfig(
        ambient_rotation=int(rec.get("ambient_rotation") or 30),
        rail=str(rec.get("rail") or "safe"),
        quiet_hours=(
            QuietHours(**(rec.get("quiet_hours") or {}))
            if rec.get("quiet_hours")
            else None
        ),
        default_vibe=str(rec.get("default_vibe") or "Calm Night"),
    )
    return {"status": "ok", "config": cfg.model_dump()}


@router.put(
    "/tv/config",
    response_model=TvConfigResponse,
    responses={200: {"model": TvConfigResponse}},
)
async def tv_put_config(
    resident_id: str | None = Query(default="me"),
    body: TVConfigUpdate = None,  # type: ignore[assignment]
):
    # Allow partial updates; merge with existing or defaults
    from app.care_store import get_tv_config, set_tv_config

    rec = await get_tv_config(resident_id or "me")
    current = TvConfig(
        ambient_rotation=int((rec or {}).get("ambient_rotation") or 30),
        rail=str((rec or {}).get("rail") or "safe"),
        quiet_hours=(
            QuietHours(**((rec or {}).get("quiet_hours") or {}))
            if (rec and rec.get("quiet_hours"))
            else None
        ),
        default_vibe=str((rec or {}).get("default_vibe") or "Calm Night"),
    )

    # Compute effective values
    new_ambient = (
        int(body.ambient_rotation)
        if body and body.ambient_rotation is not None
        else current.ambient_rotation
    )
    new_rail = (body.rail or current.rail).lower() if body else current.rail
    new_qh = (
        body.quiet_hours
        if (body and body.quiet_hours is not None)
        else current.quiet_hours
    )
    new_vibe = (
        body.default_vibe
        if (body and body.default_vibe is not None)
        else current.default_vibe
    )

    # Validate rail and simple hh:mm format for quiet hours (400 on bad input)
    rail = (new_rail or "safe").lower()
    if rail not in {"safe", "admin", "open"}:
        raise HTTPException(status_code=400, detail="invalid_rail")

    def _valid_hhmm(s: str | None) -> bool:
        if not s:
            return True
        parts = s.split(":")
        if len(parts) != 2:
            return False
        try:
            hh, mm = int(parts[0]), int(parts[1])
            return 0 <= hh <= 23 and 0 <= mm <= 59
        except Exception:
            return False

    if new_qh and not (_valid_hhmm(new_qh.start) and _valid_hhmm(new_qh.end)):
        raise HTTPException(status_code=400, detail="invalid_quiet_hours")

    await set_tv_config(
        resident_id or "me",
        ambient_rotation=int(new_ambient),
        rail=rail,
        quiet_hours=new_qh.model_dump() if new_qh else None,
        default_vibe=str(new_vibe or ""),
    )
    # Emit WS event so TV can hot-reload config without full refresh
    try:
        from app.api.care_ws import broadcast_resident

        await broadcast_resident(
            resident_id or "me",
            "tv.config.updated",
            {
                "config": {
                    "ambient_rotation": new_ambient,
                    "rail": rail,
                    "quiet_hours": new_qh.model_dump() if new_qh else None,
                    "default_vibe": new_vibe,
                }
            },
        )
    except Exception:
        pass
    return {
        "status": "ok",
        "config": {
            "ambient_rotation": new_ambient,
            "rail": rail,
            "quiet_hours": new_qh.model_dump() if new_qh else None,
            "default_vibe": new_vibe,
        },
    }

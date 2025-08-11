from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.deps.user import get_current_user_id
from app.memory.profile_store import profile_store


router = APIRouter(tags=["tv"])  # intentionally no auth deps for device-trusted kiosk


def _list_images(dir_path: Path) -> List[str]:
    try:
        files = [
            p.name
            for p in sorted(dir_path.iterdir())
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}
        ]
        return files
    except Exception:
        return []


@router.get("/tv/photos")
async def tv_photos(user_id: str = Depends(get_current_user_id)):
    """Return slideshow folder and items.

    Configure via:
      - TV_PHOTOS_DIR: absolute or relative path to image folder (default: data/shared_photos)
      - TV_PHOTOS_URL_BASE: URL base the TV app uses to fetch files (default: /shared_photos)
    """
    dir_str = os.getenv("TV_PHOTOS_DIR", "data/shared_photos")
    base_url = os.getenv("TV_PHOTOS_URL_BASE", "/shared_photos")
    dir_path = Path(dir_str)
    items = _list_images(dir_path)
    return {"folder": base_url, "items": items}


_FAV_FILE = Path(os.getenv("PHOTO_FAVORITES_STORE", "data/photo_favorites.json"))


@router.post("/tv/photos/favorite")
async def tv_photos_favorite(name: str, user_id: str = Depends(get_current_user_id)):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    try:
        _FAV_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: List[str] = []
        if _FAV_FILE.exists():
            try:
                raw = json.loads(_FAV_FILE.read_text(encoding="utf-8") or "[]")
                if isinstance(raw, list):
                    data = [str(x) for x in raw]
            except Exception:
                data = []
        if name not in data:
            data.append(name)
        _FAV_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=500, detail="persist_failed")


@router.get("/tv/weather")
async def tv_weather(user_id: str = Depends(get_current_user_id)):
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
    sentence = os.getenv("TV_WEATHER_SENTENCE", f"It's {int(round(now_temp_f))}° and {desc.lower()}.")
    return {
        "city": city,
        "now": {"temp": now_temp_f, "desc": desc, "sentence": sentence},
        "today": {"high": today_hi, "low": today_lo},
        "tomorrow": {"high": tomorrow_hi, "low": tomorrow_lo},
    }


@router.post("/tv/alert")
async def tv_alert(kind: str = "help", note: str | None = None, user_id: str = Depends(get_current_user_id)):
    """Escalation hook from TV to caregiver channel.

    This is a thin wrapper; in V1.1 we can fan-out to SMS/voice/webhook.
    """
    try:
        # Reuse caregiver API semantics locally
        return {"status": "accepted", "kind": kind, "note": note}
    except Exception:
        raise HTTPException(status_code=500, detail="alert_failed")


@router.post("/tv/music/play")
async def tv_music_play(preset: str, user_id: str = Depends(get_current_user_id)):
    """Start playing a local preset playlist (placeholder)."""
    name = (preset or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="empty_preset")
    # TODO: integrate with local player (mpv/afplay) or Spotify/Apple connectors
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


@router.post("/tv/prefs")
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


@router.post("/tv/stage2")
async def tv_stage2(
    tiles: List[str] | None = None,
    rhythm: str | None = None,
    helpfulness: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    data = {}
    if tiles is not None:
        data["preferences_tiles"] = tiles
    if rhythm is not None:
        data["daily_rhythm"] = rhythm
    if helpfulness is not None:
        data["helpfulness"] = helpfulness
    if data:
        profile_store.update(user_id, data)
    return {"status": "ok"}

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends

from app.deps.user import get_current_user_id


router = APIRouter(tags=["tv"])


# -----------------------------
# Weather (cached)
# -----------------------------

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
DEFAULT_CITY = os.getenv("CITY_NAME", "Detroit,US")
WEATHER_CACHE_PATH = Path(os.getenv("WEATHER_CACHE", "data/cache_weather.json"))
WEATHER_TTL_SECONDS = int(os.getenv("WEATHER_TTL_SECONDS", "900"))  # 15 minutes


def _read_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


async def _fetch_current(city: str) -> Optional[dict]:
    if not OPENWEATHER_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": OPENWEATHER_KEY, "units": "imperial"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


async def _fetch_forecast(city: str) -> Optional[dict]:
    if not OPENWEATHER_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"q": city, "appid": OPENWEATHER_KEY, "units": "imperial"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def _agg_today_tomorrow(forecast: dict) -> Tuple[Optional[dict], Optional[dict]]:
    if not forecast:
        return None, None
    # forecast["list"] contains 3h buckets; group by date
    by_date: Dict[str, List[float]] = {}
    for item in forecast.get("list", []) or []:
        try:
            dt_txt = item.get("dt_txt", "")
            day = dt_txt.split(" ")[0]
            t = item.get("main", {}).get("temp")
            if isinstance(t, (int, float)) and day:
                by_date.setdefault(day, []).append(float(t))
        except Exception:
            continue
    if not by_date:
        return None, None
    days_sorted = sorted(by_date.keys())
    today = _dt.date.today().isoformat()
    tomorrow = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    def _make(day: str) -> Optional[dict]:
        vals = [v for v in by_date.get(day, []) if isinstance(v, float)]
        if not vals:
            return None
        return {"high": round(max(vals)), "low": round(min(vals))}
    return _make(today), _make(tomorrow)


def _stale(ts_iso: str | None, ttl: int) -> bool:
    if not ts_iso:
        return True
    try:
        ts = _dt.datetime.fromisoformat(ts_iso)
    except Exception:
        return True
    return (_dt.datetime.utcnow() - ts).total_seconds() > ttl


@router.get("/tv/weather")
async def tv_weather(user_id: str = Depends(get_current_user_id)):
    cache = _read_json(WEATHER_CACHE_PATH)
    if not cache or _stale(cache.get("updatedAt"), WEATHER_TTL_SECONDS):
        city = DEFAULT_CITY
        current = await _fetch_current(city)
        forecast = await _fetch_forecast(city)
        now_desc = ((current or {}).get("weather") or [{}])[0].get("description") or None
        now_temp = (current or {}).get("main", {}).get("temp")
        today, tomorrow = _agg_today_tomorrow(forecast or {})
        sentence = None
        if isinstance(now_temp, (int, float)) and now_desc:
            sentence = f"{city.split(',')[0]} is {now_desc}, about {round(now_temp)}°F."
        cache = {
            "city": city,
            "now": {"temp": (round(now_temp) if isinstance(now_temp, (int, float)) else None), "desc": now_desc, "sentence": sentence},
            "today": today or {},
            "tomorrow": tomorrow or {},
            "updatedAt": _dt.datetime.utcnow().isoformat(),
        }
        _write_json(WEATHER_CACHE_PATH, cache)
    # Fallback sentence if offline
    if not (cache.get("now") or {}).get("sentence"):
        cache.setdefault("now", {})["sentence"] = "I didn’t catch the weather. Try the blue button later."
    return cache


# -----------------------------
# Calendar (read-only, next 3)
# -----------------------------

CALENDAR_FILE = Path(os.getenv("CALENDAR_FILE", "data/calendar.json"))


def _load_calendar_items() -> List[dict]:
    try:
        if CALENDAR_FILE.exists():
            data = json.loads(CALENDAR_FILE.read_text(encoding="utf-8") or "[]")
            if isinstance(data, list):
                return data
    except Exception:
        pass
    # fallback: try proactive_engine state when available
    try:
        from app.proactive_engine import STATE  # type: ignore

        ev = (STATE.get("calendar") or {}).get("events") or []
        if isinstance(ev, list):
            # normalize: dt -> date/time
            out = []
            for e in ev:
                dt: Optional[_dt.datetime] = e.get("when")
                title = e.get("title") or ""
                if isinstance(dt, _dt.datetime):
                    out.append({"date": dt.date().isoformat(), "time": dt.strftime("%H:%M"), "title": title})
            return out
    except Exception:
        pass
    return []


@router.get("/tv/calendar/next")
async def tv_calendar_next(user_id: str = Depends(get_current_user_id)):
    items = _load_calendar_items()
    today = _dt.date.today().isoformat()
    # keep events today and future, sort by date+time
    def _key(e: dict) -> Tuple[str, str]:
        return (e.get("date", ""), e.get("time", ""))

    upcoming = sorted([e for e in items if (e.get("date") or "") >= today], key=_key)[:3]
    # Return large-print friendly payload
    return {
        "items": [{"time": (e.get("time") or ""), "title": (e.get("title") or "")} for e in upcoming],
        "updatedAt": _dt.datetime.utcnow().isoformat(),
    }



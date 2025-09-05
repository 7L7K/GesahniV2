from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .deps import scheduler as sched_mod

logger = logging.getLogger(__name__)

# Live state snapshot ----------------------------------------------------------

STATE: dict[str, Any] = {
    "ha": {"entities": {}, "last_update": None},
    "weather": {"last": None, "last_update": None},
    "calendar": {"events": [], "last_update": None},
}

_SELF_REVIEW_PATH = Path(os.getenv("SELF_REVIEW_PATH", "data/self_review.json"))
_SELF_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def set_presence(kind: str, value: Any) -> None:
    STATE.setdefault("presence", {})[kind] = value
    STATE["presence"]["updated_at"] = _now_iso()


async def _update_ha_snapshot() -> None:
    try:
        from .home_assistant import get_states

        states = await get_states()
        index = {}
        for st in states:
            eid = st.get("entity_id")
            if not eid:
                continue
            index[eid] = {"state": st.get("state"), "attrs": st.get("attributes", {})}
        STATE["ha"]["entities"] = index
        STATE["ha"]["last_update"] = _now_iso()
    except Exception:
        logger.debug("_update_ha_snapshot failed", exc_info=True)


async def _update_weather() -> None:
    try:
        import httpx

        api = os.getenv("OPENWEATHER_API_KEY")
        city = os.getenv("CITY_NAME", "Detroit,US")
        if not api:
            return
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": api, "units": "imperial"},
            )
            r.raise_for_status()
            data = r.json()
        STATE["weather"]["last"] = {
            "city": city,
            "temp": data.get("main", {}).get("temp"),
            "desc": (data.get("weather") or [{}])[0].get("description"),
        }
        STATE["weather"]["last_update"] = _now_iso()
    except Exception:
        logger.debug("_update_weather failed", exc_info=True)


async def _update_calendar() -> None:
    try:
        src = os.getenv("CALENDAR_ICS_PATH") or os.getenv("CALENDAR_ICS_URL")
        if not src:
            return
        text = ""
        if src.startswith("http://") or src.startswith("https://"):
            import httpx

            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(src)
                r.raise_for_status()
                text = r.text
        else:
            p = Path(src)
            if p.exists():
                text = p.read_text(encoding="utf-8", errors="ignore")
        if not text:
            return
        # very light parse: DTSTART and SUMMARY lines
        events: list[dict] = []
        dt: str | None = None
        summary: str | None = None
        for line in text.splitlines():
            if line.startswith("DTSTART"):
                parts = line.split(":", 1)
                dt = parts[1].strip() if len(parts) > 1 else None
            elif line.startswith("SUMMARY"):
                parts = line.split(":", 1)
                summary = parts[1].strip() if len(parts) > 1 else None
            elif line.startswith("END:VEVENT"):
                if dt or summary:
                    events.append({"when": dt, "title": summary})
                dt = summary = None
        STATE["calendar"]["events"] = events[:100]
        STATE["calendar"]["last_update"] = _now_iso()
    except Exception:
        logger.debug("_update_calendar failed", exc_info=True)


async def _check_doors_unlocked() -> None:
    try:
        ents: dict[str, Any] = STATE.get("ha", {}).get("entities", {}) or {}
        unlocked: list[str] = []
        for eid, data in ents.items():
            if eid.startswith("lock.") and str(data.get("state")) == "unlocked":
                unlocked.append(eid)
        if unlocked:
            msg = {
                "type": "self_task",
                "task": "door_unlocked",
                "entities": unlocked,
                "ts": _now_iso(),
            }
            try:
                from .history import append_history

                await append_history(msg)
            except Exception:
                pass
    except Exception:
        logger.debug("_check_doors_unlocked failed", exc_info=True)


def _write_self_review() -> None:
    try:
        from . import analytics

        report = {
            "ts": _now_iso(),
            "metrics": analytics.get_metrics(),
        }
        _SELF_REVIEW_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("self_review written")
    except Exception:
        logger.debug("self_review write failed", exc_info=True)


def get_self_review() -> dict[str, Any] | None:
    try:
        if _SELF_REVIEW_PATH.exists():
            return json.loads(_SELF_REVIEW_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def startup() -> None:
    """Start scheduled proactive tasks if enabled by env flag."""

    if os.getenv("ENABLE_PROACTIVE", "0").lower() not in {"1", "true", "yes"}:
        return
    scheduler = getattr(sched_mod, "scheduler", None)
    try:
        sched_mod.start()
    except Exception:
        pass
    if not scheduler or not hasattr(scheduler, "add_job"):
        logger.debug("scheduler unavailable; proactive engine disabled")
        return

    try:
        # Chaos injection for scheduler failures
        from .chaos import chaos_scheduler_operation

        async def chaotic_update_ha_snapshot():
            await chaos_scheduler_operation("update_ha_snapshot", _update_ha_snapshot)

        # Poll HA snapshot every 60s
        scheduler.add_job(
            lambda: asyncio.create_task(chaotic_update_ha_snapshot()),
            trigger="interval",
            seconds=60,
            id="proactive_ha_snapshot",
            replace_existing=True,
        )
        # Weather every 15 minutes
        scheduler.add_job(
            lambda: asyncio.create_task(_update_weather()),
            trigger="interval",
            minutes=15,
            id="proactive_weather",
            replace_existing=True,
        )
        # Calendar every 5 minutes
        scheduler.add_job(
            lambda: asyncio.create_task(_update_calendar()),
            trigger="interval",
            minutes=5,
            id="proactive_calendar",
            replace_existing=True,
        )
        # Self task: check doors every 5 minutes
        scheduler.add_job(
            lambda: asyncio.create_task(_check_doors_unlocked()),
            trigger="interval",
            minutes=5,
            id="proactive_check_doors",
            replace_existing=True,
        )
        # Daily self-review at 03:30
        scheduler.add_job(
            _write_self_review,
            trigger="cron",
            hour=3,
            minute=30,
            id="proactive_self_review",
            replace_existing=True,
        )
        logger.info("Proactive engine scheduled")
    except Exception:
        logger.debug("proactive scheduling failed", exc_info=True)


def on_ha_event(event: dict[str, Any]) -> None:
    # Best-effort in-memory update for specific entity change events
    try:
        eid = event.get("entity_id")
        state = event.get("state")
        if eid and STATE.get("ha"):
            STATE["ha"].setdefault("entities", {})[eid] = state
            STATE["ha"]["last_update"] = _now_iso()
    except Exception:
        pass


__all__ = ["startup", "STATE", "set_presence", "on_ha_event", "get_self_review"]

import os
import time
from dataclasses import dataclass

from .budget import get_budget_state
from .home_assistant import call_service, get_states
from .memory.profile_store import profile_store
from .memory.vector_store import add_user_memory


@dataclass
class Snapshot:
    user_id: str
    created_at: float
    presence_ok: bool | None = None
    weather: dict[str, Any] | None = None
    calendar: dict[str, Any] | None = None


_SNAP: dict[str, tuple[Snapshot, float]] = {}
_TTL = float(os.getenv("PROACTIVE_SNAPSHOT_TTL", "600"))


def _now() -> float:
    return time.time()


async def _fetch_presence(user_id: str) -> bool | None:  # stubs; to be extended
    return True


async def _fetch_weather(user_id: str) -> dict[str, Any] | None:
    return {"temp": None}


async def _fetch_calendar(user_id: str) -> dict[str, Any] | None:
    return {}


async def refresh_snapshot(user_id: str) -> Snapshot:
    now = _now()
    snap, exp = _SNAP.get(user_id, (None, 0.0))  # type: ignore
    if snap is not None and now < exp:
        return snap
    presence = await _fetch_presence(user_id)
    weather = await _fetch_weather(user_id)
    calendar = await _fetch_calendar(user_id)
    snap = Snapshot(
        user_id=user_id,
        created_at=now,
        presence_ok=presence,
        weather=weather,
        calendar=calendar,
    )
    _SNAP[user_id] = (snap, now + _TTL)
    return snap


def _dynamic_tau(user_id: str) -> float:
    # Tighten when budget near soft cap; else median 0.6
    try:
        st = get_budget_state(user_id)
        return 0.7 if st.get("reply_len_target") == "short" else 0.6
    except Exception:
        return 0.6


def _is_anomalous(snap: Snapshot) -> bool:
    # Placeholder rolling baseline check; hook real stats later
    return False


def _missing_profile_key(user_id: str) -> str | None:
    prof = profile_store.get(user_id)
    for key in ("night_temp", "wake_time"):
        if key not in prof:
            return key
    return None


async def maybe_curiosity_prompt(
    user_id: str, last_confidence: float | None
) -> str | None:
    tau = _dynamic_tau(user_id)
    need = _missing_profile_key(user_id)
    snap = await refresh_snapshot(user_id)
    if (
        (last_confidence is not None and last_confidence < tau)
        or need
        or _is_anomalous(snap)
    ):
        if need:
            return f"Quick question: what's your {need.replace('_', ' ')}?"
        return "Quick check-in: anything you'd like to adjust for tonight?"
    return None


def handle_user_reply(user_id: str, text: str) -> None:
    # naive extraction: key: value → treat as profile fact upsert
    parts = text.split(":", 1)
    if len(parts) == 2:
        key = parts[0].strip().lower().replace(" ", "_")
        val = parts[1].strip()
        try:
            from .memory.write_policy import memory_write_policy

            if memory_write_policy.should_write_profile(text, key):
                profile_store.upsert(user_id, key, val, source="utterance")
        except Exception:
            # fallback legacy setter
            profile_store.set(user_id, key, val)
        try:
            from .memory.write_policy import memory_write_policy

            if memory_write_policy.should_write_memory(text):
                add_user_memory(user_id, f"{key} = {val}")
        except Exception:
            pass


def set_presence(user_id: str, ok: bool) -> None:
    now = _now()
    snap, _ = _SNAP.get(user_id, (Snapshot(user_id=user_id, created_at=now), 0.0))
    snap.presence_ok = ok
    snap.created_at = now
    _SNAP[user_id] = (snap, now + _TTL)


async def _is_unlocked(entity_id: str) -> bool:
    try:
        states = await get_states()
        for st in states:
            if st.get("entity_id") == entity_id:
                return (st.get("state") or "").lower() == "unlocked"
    except Exception:
        pass
    return False


async def _notify_unlock(entity_id: str) -> None:
    # Persistent notification in HA
    try:
        await call_service(
            "persistent_notification",
            "create",
            {
                "title": "Door left unlocked",
                "message": f"{entity_id} has been unlocked for 10 minutes.",
            },
        )
    except Exception:
        pass


async def _lock_if_still_unlocked(entity_id: str) -> None:
    try:
        if await _is_unlocked(entity_id):
            await call_service("lock", "lock", {"entity_id": entity_id})
    except Exception:
        pass


def _start_scheduler() -> None:
    try:
        sched_mod.start()
        scheduler = getattr(sched_mod, "scheduler", None)
        if scheduler and hasattr(scheduler, "add_job"):
            # Hourly persistence
            scheduler.add_job(
                profile_store.persist_all,
                trigger="cron",
                minute=0,
                id="profile_persist_hourly",
                replace_existing=True,
            )
    except Exception:
        # optional dependency; ignore in tests
        pass


def startup() -> None:
    _start_scheduler()


def on_ha_event(event: dict[str, Any]) -> None:
    """Lightweight HA event handler for proactive self-tasks.

    Expects events with keys: "entity_id", "new_state", "old_state".
    When a lock is unlocked, schedules notification after 10 minutes and a
    safety re-lock 2 minutes later if still unlocked.
    """
    try:
        entity_id = (event.get("entity_id") or "").strip()
        new_state = (event.get("new_state") or "").lower()
        if not entity_id or "." not in entity_id:
            return
        domain = entity_id.split(".", 1)[0]
        if domain != "lock":
            return
        if new_state != "unlocked":
            return
        # Schedule follow-ups
        try:
            scheduler = getattr(sched_mod, "scheduler", None)
            if scheduler and hasattr(scheduler, "add_job"):
                scheduler.add_job(
                    _notify_unlock,
                    trigger="date",
                    seconds=600,
                    args=[entity_id],
                    id=f"notify_unlock_{entity_id}",
                    replace_existing=True,
                )
                scheduler.add_job(
                    _lock_if_still_unlocked,
                    trigger="date",
                    seconds=720,
                    args=[entity_id],
                    id=f"auto_lock_{entity_id}",
                    replace_existing=True,
                )
        except Exception:
            pass
    except Exception:
        pass


__all__ = [
    "maybe_curiosity_prompt",
    "handle_user_reply",
    "refresh_snapshot",
    "startup",
    "set_presence",
    "on_ha_event",
]

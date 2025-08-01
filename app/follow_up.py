import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from .history import append_history

# ---------------------------------------------------------------------------
# Config and persistence
# ---------------------------------------------------------------------------

FOLLOW_UPS_FILE = Path(
    os.getenv("FOLLOW_UPS_FILE", Path(__file__).resolve().parent.parent / "data" / "follow_ups.json")
)
FOLLOW_UPS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Ensure an event loop exists for the scheduler, even during import-time
try:
    _loop = asyncio.get_event_loop()
except RuntimeError:
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

_scheduler = AsyncIOScheduler(event_loop=_loop)
_scheduler.start()

_lock = asyncio.Lock()


def _load_followups() -> List[Dict[str, Any]]:
    if FOLLOW_UPS_FILE.exists():
        try:
            return json.loads(FOLLOW_UPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_followups(entries: List[Dict[str, Any]]) -> None:
    FOLLOW_UPS_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


async def _fire_followup(prompt: str, session_id: str, fid: str) -> None:
    """Executed by the scheduler: send reminder and remove from store."""
    await append_history(
        {
            "event": "follow_up",
            "session_id": session_id,
            "follow_up_id": fid,
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    )
    async with _lock:
        data = _load_followups()
        data = [e for e in data if e["id"] != fid]
        _save_followups(data)


def _schedule(entry: Dict[str, Any]) -> None:
    run_date = datetime.fromisoformat(entry["when"])
    _scheduler.add_job(
        _fire_followup,
        trigger=DateTrigger(run_date=run_date),
        id=entry["id"],
        args=[entry["prompt"], entry["session_id"], entry["id"]],
        replace_existing=True,
    )


# Rehydrate jobs on import
for _entry in _load_followups():
    try:
        if datetime.fromisoformat(_entry["when"]) > datetime.utcnow():
            _schedule(_entry)
    except Exception:
        continue


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def schedule_follow_up(prompt: str, when: datetime | str, session_id: str) -> str:
    """Schedule a follow-up reminder and persist it.

    Returns the follow-up ID.
    """
    when_dt = datetime.fromisoformat(when) if isinstance(when, str) else when
    fid = uuid4().hex
    entry = {
        "id": fid,
        "prompt": prompt,
        "when": when_dt.isoformat(),
        "session_id": session_id,
    }
    _schedule(entry)
    async def _save_and_log() -> None:
        async with _lock:
            data = _load_followups()
            data.append(entry)
            _save_followups(data)
        await append_history({
            "event": "schedule_follow_up",
            "session_id": session_id,
            "follow_up_id": fid,
            "prompt": prompt,
            "when": entry["when"],
        })
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_save_and_log())
    else:
        loop.create_task(_save_and_log())
    return fid


def list_follow_ups(session_id: str | None = None) -> List[Dict[str, Any]]:
    """Return all follow-ups, optionally filtered by session."""
    entries = _load_followups()
    if session_id is not None:
        entries = [e for e in entries if e["session_id"] == session_id]
    return entries


def cancel_follow_up(fid: str) -> bool:
    """Cancel a scheduled follow-up by ID."""
    removed = False
    async def _cancel() -> None:
        nonlocal removed
        async with _lock:
            data = _load_followups()
            new = []
            for e in data:
                if e["id"] == fid:
                    removed = True
                else:
                    new.append(e)
            if removed:
                _save_followups(new)
        if removed:
            await append_history({"event": "cancel_follow_up", "follow_up_id": fid})
    try:
        _scheduler.remove_job(fid)
    except Exception:
        pass
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_cancel())
    else:
        loop.create_task(_cancel())
    return removed


scheduler = _scheduler

__all__ = ["schedule_follow_up", "list_follow_ups", "cancel_follow_up", "scheduler"]

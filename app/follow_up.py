import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.date import DateTrigger
except Exception:  # pragma: no cover - optional dependency

    class AsyncIOScheduler:  # minimal stub
        def __init__(self, *a, **k):
            self.running = False
            self._jobs: dict[str, Any] = {}

        def start(self):
            self.running = True

        def add_job(
            self, func, trigger=None, id=None, args=None, replace_existing=False, **kw
        ):
            self._jobs[id] = {"func": func, "trigger": trigger, "args": args or []}

        def remove_job(self, id):
            self._jobs.pop(id, None)

        def get_job(self, id):
            return self._jobs.get(id)

        def shutdown(self, wait=True):
            self._jobs.clear()
            self.running = False

    class DateTrigger:  # pragma: no cover - simple container
        def __init__(self, run_date=None):
            self.run_date = run_date


from .history import append_history


def _in_test_mode() -> bool:
    v = lambda s: str(os.getenv(s, "")).strip().lower()
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("PYTEST_RUNNING")
        or v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or v("ENV") == "test"
    )

# ---------------------------------------------------------------------------
# Config and persistence
# ---------------------------------------------------------------------------

FOLLOW_UPS_FILE = Path(
    os.getenv(
        "FOLLOW_UPS_FILE",
        Path(__file__).resolve().parent.parent / "data" / "follow_ups.json",
    )
)
FOLLOW_UPS_FILE.parent.mkdir(parents=True, exist_ok=True)

# Initialize scheduler conservatively in tests to avoid manipulating the global
# event loop policy/runtime when importing this module under pytest.
if _in_test_mode():
    try:
        _loop = asyncio.get_event_loop()
    except RuntimeError:
        _loop = None  # don't create/set a loop in tests; remain lazy
    _scheduler = AsyncIOScheduler(event_loop=_loop)  # type: ignore[arg-type]
else:
    try:
        _loop = asyncio.get_event_loop()
    except RuntimeError:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    _scheduler = AsyncIOScheduler(event_loop=_loop)
    _scheduler.start()

_lock = asyncio.Lock()


def _load_followups() -> list[dict[str, Any]]:
    if FOLLOW_UPS_FILE.exists():
        try:
            return json.loads(FOLLOW_UPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_followups(entries: list[dict[str, Any]]) -> None:
    FOLLOW_UPS_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _schedule(entry: dict[str, Any]) -> None:
    run_date = datetime.fromisoformat(entry["when"])
    _scheduler.add_job(
        _fire_followup,
        trigger=DateTrigger(run_date=run_date),
        id=entry["id"],
        args=[entry["prompt"], entry["session_id"], entry["id"]],
        replace_existing=True,
    )


# Rehydrate jobs on import (skip during tests to avoid side effects)
if not _in_test_mode():
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
        await append_history(
            {
                "event": "schedule_follow_up",
                "session_id": session_id,
                "follow_up_id": fid,
                "prompt": prompt,
                "when": entry["when"],
            }
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_save_and_log())
    else:
        loop.create_task(_save_and_log())
    return fid


def list_follow_ups(session_id: str | None = None) -> list[dict[str, Any]]:
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

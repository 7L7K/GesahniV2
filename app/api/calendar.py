from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends

from app.deps.user import get_current_user_id


router = APIRouter(tags=["Calendar"])


CALENDAR_FILE = Path(os.getenv("CALENDAR_FILE", "data/calendar.json"))


def _read() -> List[dict]:
    try:
        if CALENDAR_FILE.exists():
            data = json.loads(CALENDAR_FILE.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


@router.get("/calendar/next")
async def next_three(user_id: str = Depends(get_current_user_id)):
    today = _dt.date.today().isoformat()
    items = [e for e in _read() if (e.get("date") or "") >= today]
    items.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    return {"items": items[:3]}



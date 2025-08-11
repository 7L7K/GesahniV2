from __future__ import annotations

import json
from fastapi import APIRouter, Depends, Query
from app.deps.user import get_current_user_id
from app.history import HISTORY_FILE

router = APIRouter(tags=["history"])


@router.get("/history/recent")
async def recent_history(
    limit: int = Query(default=50, ge=1, le=1000),
    user_id: str = Depends(get_current_user_id),
):
    path = HISTORY_FILE
    if not path.exists():
        return {"items": []}
    text = path.read_text(encoding="utf-8")
    items: list[dict] = []
    if path.suffix == ".json":
        try:
            data = json.loads(text) if text else []
            if isinstance(data, list):
                items = [x for x in data if isinstance(x, dict)]
        except Exception:
            items = []
    else:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
            except Exception:
                continue
            if len(items) >= limit:
                break
    return {"items": list(reversed(items[-limit:]))}



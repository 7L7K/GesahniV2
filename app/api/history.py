from __future__ import annotations

import json
from fastapi import APIRouter, Depends, Query, HTTPException
from app.deps.user import get_current_user_id
from app.history import HISTORY_FILE
from app.deps.scopes import optional_require_scope

router = APIRouter(tags=["Admin"])


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


@router.post("/history/pin", dependencies=[Depends(optional_require_scope("pin"))])
async def pin_interaction(
    session_id: str,
    hash_value: str,
    user_id: str = Depends(get_current_user_id),
):
    """Pin an interaction by hash into the pinned store (requires 'pin' scope when scopes enforced)."""
    try:
        from app.memory.memgpt import memgpt
        # Best-effort: iterate recent store and find by hash
        items = memgpt.retrieve_relevant_memories(hash_value)
        if not items:
            raise HTTPException(status_code=404, detail="not_found")
        item = items[0]
        memgpt.store_interaction(item.get("prompt", ""), item.get("answer", ""), session_id, user_id=user_id, tags=["pin"])
        return {"status": "pinned"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="error")


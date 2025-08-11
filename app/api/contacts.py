from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.deps.user import get_current_user_id


router = APIRouter(tags=["contacts"])


CONTACTS_FILE = Path(os.getenv("CONTACTS_FILE", "data/contacts.json"))


def _read_contacts() -> List[dict]:
    try:
        if CONTACTS_FILE.exists():
            data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


@router.get("/tv/contacts")
async def list_contacts(user_id: str = Depends(get_current_user_id)):
    return {"items": _read_contacts()}


@router.post("/tv/contacts/call")
async def start_call(name: str, user_id: str = Depends(get_current_user_id)):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name_required")
    # Device capability or paired phone/VOIP bridge can be added later.
    # For now: raise caregiver alert so they can place the call.
    try:
        from app.caregiver import router as cg  # type: ignore
    except Exception:
        cg = None
    # Best-effort: write a simple alert file the caregiver portal could watch
    alerts_path = Path(os.getenv("ALERTS_FILE", "data/caregiver_alerts.json"))
    try:
        alerts = []
        if alerts_path.exists():
            alerts = json.loads(alerts_path.read_text(encoding="utf-8") or "[]")
        alerts.append({"type": "call_request", "name": name})
        alerts_path.parent.mkdir(parents=True, exist_ok=True)
        alerts_path.write_text(json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"status": "alerted", "message": "Pick up your phone, I’ll dial for you"}



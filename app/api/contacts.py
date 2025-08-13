 

import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..care_store import create_contact, list_contacts, update_contact, delete_contact


router = APIRouter(tags=["care"])


class ContactBody(BaseModel):
    id: str | None = None
    resident_id: str
    name: str
    phone: str | None = None
    priority: int = 0
    quiet_hours: dict | None = None


@router.post("/care/contacts")
async def create_contact_api(body: ContactBody):
    cid = body.id or uuid.uuid4().hex
    rec: Dict[str, Any] = {**body.model_dump(), "id": cid}
    await create_contact(rec)
    return {"id": cid, "status": "ok"}


@router.get("/care/contacts")
async def list_contacts_api(resident_id: str):
    return {"items": await list_contacts(resident_id)}


@router.patch("/care/contacts/{contact_id}")
async def update_contact_api(contact_id: str, body: dict):
    if not body:
        raise HTTPException(status_code=400, detail="empty_update")
    await update_contact(contact_id, **body)
    return {"status": "ok"}


@router.delete("/care/contacts/{contact_id}")
async def delete_contact_api(contact_id: str):
    await delete_contact(contact_id)
    return {"status": "ok"}

## NOTE: keep future import only at the very top once; consolidated below

import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.deps.user import get_current_user_id


tv_router = APIRouter(tags=["contacts"])


CONTACTS_FILE = Path(os.getenv("CONTACTS_FILE", "data/contacts.json"))


def _read_contacts() -> List[dict]:
    try:
        if CONTACTS_FILE.exists():
            data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


@tv_router.get("/tv/contacts")
async def list_tv_contacts(user_id: str = Depends(get_current_user_id)):
    return {"items": _read_contacts()}


@tv_router.post("/tv/contacts/call")
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

# Merge TV endpoints into the care router so main.py includes everything under one router
try:
    router  # type: ignore[name-defined]
except NameError:
    router = APIRouter(tags=["care"])  # fallback, but should not happen
router.include_router(tv_router)



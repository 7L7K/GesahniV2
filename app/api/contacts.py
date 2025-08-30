import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.deps.scopes import docs_security_with

from ..care_store import create_contact, delete_contact, list_contacts, update_contact

router = APIRouter(
    tags=["Care"], dependencies=[Depends(docs_security_with(["care:resident"]))]
)


class ContactBody(BaseModel):
    id: str | None = None
    resident_id: str
    name: str
    phone: str | None = None
    priority: int = 0
    quiet_hours: dict | None = None

    # Example shown in OpenAPI
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resident_id": "r1",
                "name": "Leola",
                "phone": "+15551234567",
                "priority": 10,
                "quiet_hours": {"start": "22:00", "end": "06:00"},
            }
        }
    )


class ContactCreateResponse(BaseModel):
    id: str
    status: str = "ok"

    model_config = ConfigDict(
        json_schema_extra={"example": {"id": "c_01HXYZABCD", "status": "ok"}}
    )


@router.post(
    "/care/contacts",
    response_model=ContactCreateResponse,
    responses={200: {"model": ContactCreateResponse}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "resident_id": "r1",
                            "name": "Leola",
                            "phone": "+15551234567",
                            "priority": 10,
                            "quiet_hours": {"start": "22:00", "end": "06:00"},
                        }
                    }
                }
            }
        }
    },
)
async def create_contact_api(body: ContactBody):
    cid = body.id or uuid.uuid4().hex
    rec: dict[str, Any] = {**body.model_dump(), "id": cid}
    await create_contact(rec)
    return {"id": cid, "status": "ok"}


@router.get("/care/contacts")
async def list_contacts_api(resident_id: str):
    return {"items": await list_contacts(resident_id)}


class ContactUpdateResponse(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


@router.patch(
    "/care/contacts/{contact_id}",
    response_model=ContactUpdateResponse,
    responses={200: {"model": ContactUpdateResponse}},
)
async def update_contact_api(contact_id: str, body: dict):
    if not body:
        raise HTTPException(status_code=400, detail="empty_update")
    await update_contact(contact_id, **body)
    return {"status": "ok"}


@router.delete(
    "/care/contacts/{contact_id}",
    response_model=ContactUpdateResponse,
    responses={200: {"model": ContactUpdateResponse}},
)
async def delete_contact_api(contact_id: str):
    await delete_contact(contact_id)
    return {"status": "ok"}


## NOTE: keep future import only at the very top once; consolidated below

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from app.deps.user import get_current_user_id

tv_router = APIRouter(
    tags=["TV"], dependencies=[Depends(docs_security_with(["care:resident"]))]
)


CONTACTS_FILE = Path(os.getenv("CONTACTS_FILE", "data/contacts.json"))


def _read_contacts() -> list[dict]:
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


@tv_router.post(
    "/tv/contacts/call",
    response_model=ContactUpdateResponse,
    responses={200: {"model": ContactUpdateResponse}},
)
async def start_call(
    body: dict | None = None,
    name: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    # Prefer JSON body { name }, fall back to query param for backward compat
    if body and isinstance(body, dict) and not name:
        name = str(body.get("name") or "")
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name_required")
    # Device capability or paired phone/VOIP bridge can be added later.
    # For now: raise caregiver alert so they can place the call.
    try:
        from app.caregiver import router as _cg  # type: ignore
    except Exception:
        _cg = None
    # Best-effort: write a simple alert file the caregiver portal could watch
    alerts_path = Path(os.getenv("ALERTS_FILE", "data/caregiver_alerts.json"))
    try:
        alerts = []
        if alerts_path.exists():
            alerts = json.loads(alerts_path.read_text(encoding="utf-8") or "[]")
        alerts.append({"type": "call_request", "name": name})
        alerts_path.parent.mkdir(parents=True, exist_ok=True)
        alerts_path.write_text(
            json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    return {"status": "alerted", "message": "Pick up your phone, I’ll dial for you"}


# Merge TV endpoints into the care router so main.py includes everything under one router
router.include_router(tv_router)

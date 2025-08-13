from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.deps.user import get_current_user_id


router = APIRouter(tags=["Calendar"])

REMINDERS_STORE = Path(os.getenv("REMINDERS_STORE", "data/reminders.json"))


def _read() -> List[dict]:
    if REMINDERS_STORE.exists():
        try:
            return json.loads(REMINDERS_STORE.read_text(encoding="utf-8") or "[]")
        except Exception:
            return []
    return []


def _write(data: List[dict]) -> None:
    REMINDERS_STORE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/reminders")
async def list_reminders(user_id: str = Depends(get_current_user_id)):
    # Single-device scope: return all reminders (later: per-user)
    return {"items": _read()}


@router.post("/reminders")
class ReminderCreate(BaseModel):
    text: str

    model_config = ConfigDict(json_schema_extra={"example": {"text": "Take meds at 9pm"}})


class OkResponse(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


@router.post("/reminders", response_model=OkResponse, responses={200: {"model": OkResponse}})
async def add_reminder(text: str | None = None, body: ReminderCreate | None = None, user_id: str = Depends(get_current_user_id)):
    text = (text or "").strip()
    if not text and body and getattr(body, "text", None):
        text = str(body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty")
    data = _read()
    item = {"text": text}
    data.append(item)
    _write(data)
    return {"status": "ok"}


@router.delete("/reminders")
async def clear_reminders(user_id: str = Depends(get_current_user_id)):
    _write([])
    return {"status": "ok"}




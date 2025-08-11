"""Caregiver portal backend routes scaffold.

Includes: sessions list, contacts manage placeholder, device status, alerts.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/caregiver", tags=["admin"])


@router.get("/sessions")
async def list_sessions() -> dict:
    return {"sessions": []}


@router.get("/device_status")
async def device_status() -> dict:
    return {"online": True}


@router.post("/alert")
async def raise_alert(kind: str = "help", note: str | None = None) -> dict:
    # Placeholder for escalation channel (SMS/call/webhook)
    return {"status": "accepted", "kind": kind, "note": note}



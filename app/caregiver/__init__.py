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



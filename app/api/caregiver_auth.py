from __future__ import annotations

import hmac
import hashlib
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict


router = APIRouter(tags=["Care"])


def _hmac(data: str, key: str) -> str:
    return hmac.new(key.encode(), data.encode(), hashlib.sha256).hexdigest()


def _secret() -> str:
    return os.getenv("CARE_ACK_SECRET", os.getenv("JWT_SECRET", "change-me"))


@router.get("/care/ack_token")
async def create_ack_token(alert_id: str, ttl_seconds: int = 300) -> dict:
    # Generates a short-lived token the caregiver can use without login
    exp = int(time.time()) + max(60, min(3600, int(ttl_seconds)))
    payload = f"{alert_id}:{exp}"
    sig = _hmac(payload, _secret())
    return {"token": f"{payload}:{sig}"}


def verify_ack_token(token: str) -> str:
    try:
        alert_id, exp_s, sig = token.split(":", 2)
        exp = int(exp_s)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_token")
    if int(time.time()) > exp:
        raise HTTPException(status_code=400, detail="expired_token")
    if not hmac.compare_digest(sig, _hmac(f"{alert_id}:{exp}", _secret())):
        raise HTTPException(status_code=400, detail="invalid_token")
    return alert_id


class AckViaLinkResponse(BaseModel):
    status: str
    id: str | None = None
    resident_id: str | None = None
    kind: str | None = None
    severity: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "acknowledged",
                "id": "a_01HXYZ",
                "resident_id": "r1",
                "kind": "help",
                "severity": "critical",
            }
        }
    )


@router.post("/care/alerts/ack_via_link", responses={200: {"model": AckViaLinkResponse}})
async def ack_via_link(token: str):
    from .care import ack_alert  # avoid circular import at module import time
    alert_id = verify_ack_token(token)
    # Pass-through to core ack endpoint (no requester identity for MVP)
    return await ack_alert(alert_id, None)



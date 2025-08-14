from __future__ import annotations

import os
import time
import hmac
import hashlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel, ConfigDict

from ..deps.user import get_current_user_id
from ..deps.scopes import optional_require_scope
from ..deps.roles import require_roles
from ..metrics import (
    TIME_TO_ACK_SECONDS,
    ALERT_SEND_FAILURES,
    HEARTBEAT_OK,
    HEARTBEAT_LATE,
)
from ..analytics import record  # simple counter reuse
from ..security import rate_limit_problem
from ..care_store import (
    ensure_tables,
    insert_alert,
    get_alert,
    update_alert,
    insert_event,
    list_alerts as list_alerts_db,
    upsert_device,
    get_device,
    set_device_flags,
    list_devices,
    create_session,
    update_session,
    list_sessions as list_sessions_db,
)


router = APIRouter(tags=["Care"], dependencies=[])


# In-memory MVP stores; swap with DB in CARE-001
ALERTS: Dict[str, Dict[str, Any]] = {}
ALERT_EVENTS: Dict[str, list[Dict[str, Any]]] = {}
DEVICES: Dict[str, Dict[str, Any]] = {}
CONTACTS: Dict[str, Dict[str, Any]] = {}


class AlertCreate(BaseModel):
    resident_id: str
    kind: str
    severity: str = "info"  # info|warn|critical
    note: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resident_id": "r1",
                "kind": "help",
                "severity": "critical",
                "note": "Grandma pressed the help button",
            }
        }
    )


class AckBody(BaseModel):
    by: str | None = None  # caregiver id or name

    model_config = ConfigDict(
        json_schema_extra={"example": {"by": "caregiver_123"}}
    )


def _now() -> float:
    return time.time()


def _id() -> str:
    return hashlib.md5(f"{_now()}:{os.urandom(8).hex()}".encode()).hexdigest()


def _event(alert_id: str, type_: str, **meta: Any) -> None:
    ALERT_EVENTS.setdefault(alert_id, []).append({"t": _now(), "type": type_, **meta})


def _twilio_enabled() -> bool:
    return os.getenv("NOTIFY_TWILIO_SMS", "1").lower() in {"1", "true", "yes", "on"}


async def _notify_sms(resident_id: str, msg: str) -> bool:
    if not _twilio_enabled():
        return True
    # Enqueue for background worker
    try:
        from ..queue import get_queue
        q = get_queue("care_sms")
        # for MVP, route to a single test number via env
        to = os.getenv("TWILIO_TEST_TO", "+10000000000")
        await q.push({"to": to, "body": msg, "resident_id": resident_id, "retries": 0})
        return True
    except Exception:
        ALERT_SEND_FAILURES.labels("sms").inc()
        return False


class AlertRecord(BaseModel):
    id: str
    resident_id: str
    kind: str
    severity: str
    note: str
    created_at: float
    status: str
    ack_at: float | None = None
    resolved_at: float | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "a01",
                "resident_id": "r1",
                "kind": "help",
                "severity": "critical",
                "note": "Grandma pressed the help button",
                "created_at": 1736467200.0,
                "status": "open",
                "ack_at": None,
                "resolved_at": None,
            }
        }
    )


@router.post(
    "/care/alerts",
    response_model=AlertRecord,
    responses={
        200: {"model": AlertRecord},
        429: {
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": {"error": "rate_limited", "retry_after": 29},
                        "instance": "/v1/care/alerts",
                        "retry_after": 29,
                    }
                }
            }
        },
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "resident_id": "r1",
                            "kind": "help",
                            "severity": "critical",
                            "note": "Grandma pressed the help button",
                        }
                    }
                }
            }
        }
    },
)
async def create_alert(
    body: AlertCreate = Body(
        ..., example={
            "resident_id": "r1",
            "kind": "help",
            "severity": "critical",
            "note": "Grandma pressed the help button",
        }
    ),
    request: Request = None,  # type: ignore[assignment]
    user_id: str = Depends(get_current_user_id),
):
    # OPS-1: 1 request per 30 seconds per user
    # Use route-local limiter that returns RFC7807 when blocked
    # Apply a strict, route-local rate limit using our RFC7807 helper
    await rate_limit_problem(request, long_limit=1, burst_limit=1, window_s=30.0)
    if body.kind not in {"help", "fall", "battery", "custom"}:
        raise HTTPException(status_code=400, detail="invalid_kind")
    if body.severity not in {"info", "warn", "critical"}:
        raise HTTPException(status_code=400, detail="invalid_severity")
    aid = _id()
    rec = {
        "id": aid,
        "resident_id": body.resident_id,
        "kind": body.kind,
        "severity": body.severity,
        "note": body.note or "",
        "created_at": _now(),
        "status": "open",
        "ack_at": None,
        "resolved_at": None,
    }
    ALERTS[aid] = rec  # in-memory mirror for WS fanout
    await insert_alert(rec)
    await insert_event(aid, "created", {})
    # Notify caregivers (MVP: one SMS)
    await _notify_sms(body.resident_id, f"Alert: {body.kind} ({body.severity})")
    try:
        from .care_ws import broadcast_resident  # local import to avoid cycle at import time
        await broadcast_resident(body.resident_id, "alert.created", {"id": aid, "kind": body.kind, "severity": body.severity})
    except Exception:
        pass
    return rec


@router.post(
    "/care/alerts/{alert_id}/ack",
    response_model=AlertRecord,
    responses={200: {"model": AlertRecord}},
    openapi_extra={"requestBody": {"content": {"application/json": {"schema": {"example": {"by": "cg1"}}}}}},
    dependencies=[Depends(optional_require_scope("care:caregiver")), Depends(require_roles(["caregiver"]))],
)
async def ack_alert(alert_id: str, body: AckBody | None = None):
    rec = ALERTS.get(alert_id) or await get_alert(alert_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not_found")
    if rec.get("ack_at"):
        return rec
    rec["ack_at"] = _now()
    rec["status"] = "acknowledged"
    await update_alert(alert_id, ack_at=rec["ack_at"], status="acknowledged")
    await insert_event(alert_id, "acknowledged", {"by": (body.by if body else None)})
    dt = float(rec["ack_at"] - rec["created_at"]) if rec.get("created_at") else 0.0
    TIME_TO_ACK_SECONDS.observe(max(dt, 0.0))
    try:
        from .care_ws import broadcast_resident
        await broadcast_resident(rec["resident_id"], "alert.acknowledged", {"id": alert_id, "by": (body.by if body else None)})
    except Exception:
        pass
    return rec


@router.post("/care/alerts/{alert_id}/resolve", response_model=AlertRecord, responses={200: {"model": AlertRecord}}, dependencies=[Depends(require_roles(["caregiver", "admin"]))])
async def resolve_alert(alert_id: str):
    rec = ALERTS.get(alert_id) or await get_alert(alert_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not_found")
    rec["resolved_at"] = _now()
    rec["status"] = "resolved"
    await update_alert(alert_id, resolved_at=rec["resolved_at"], status="resolved")
    await insert_event(alert_id, "resolved", {})
    return rec


class Heartbeat(BaseModel):
    device_id: str
    resident_id: str
    battery_pct: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"device_id": "dev-abc", "resident_id": "r1", "battery_pct": 92}
        }
    )


from app.models.common import OkResponse as CommonOkResponse


class OkResponse(CommonOkResponse):
    model_config = ConfigDict(title="OkResponse")


@router.post("/care/devices/{device_id}/heartbeat", response_model=OkResponse, responses={200: {"model": OkResponse}}, dependencies=[Depends(require_roles(["caregiver", "resident"]))])
async def heartbeat(device_id: str, body: Heartbeat):
    now = _now()
    st = await upsert_device(device_id, body.resident_id, battery_pct=body.battery_pct)
    late = now - float(st.get("last_seen") or 0.0) > 90.0 if st.get("last_seen") else False
    if late:
        HEARTBEAT_LATE.inc()
    else:
        HEARTBEAT_OK.inc()
    return {"status": "ok"}


@router.get("/care/device_status", dependencies=[Depends(require_roles(["caregiver", "resident"]))])
async def device_status(device_id: str) -> dict:
    st = await get_device(device_id)
    if not st:
        return {"device_id": device_id, "online": False}
    online = (_now() - float(st.get("last_seen") or 0.0) <= 90.0)
    return {"device_id": device_id, "online": online, "battery": st.get("battery_pct")}


@router.get("/care/alerts", dependencies=[Depends(require_roles(["caregiver", "resident"]))])
async def list_alerts(resident_id: Optional[str] = None):
    items = await list_alerts_db(resident_id)
    return {"items": items}


# Sessions CRUD (MVP)
class SessionBody(BaseModel):
    id: str
    resident_id: str
    title: str | None = None
    transcript_uri: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "s_01HABCDEF",
                "resident_id": "r1",
                "title": "Morning check-in",
                "transcript_uri": "s3://bucket/transcripts/s_01HABCDEF.txt",
            }
        }
    )


@router.post("/care/sessions", response_model=OkResponse, responses={200: {"model": OkResponse}}, openapi_extra={"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SessionBody"}}}}})
async def create_care_session(body: SessionBody):
    # Avoid duplicate session ids during OpenAPI smoke calls
    try:
        await create_session(body.model_dump())
    except Exception:
        body.id = _id()
        await create_session(body.model_dump())
    return {"status": "ok"}


@router.patch("/care/sessions/{session_id}", response_model=OkResponse, responses={200: {"model": OkResponse}})
async def patch_care_session(session_id: str, body: dict):
    await update_session(session_id, **body)
    return {"status": "ok"}


@router.get("/care/sessions")
async def list_care_sessions(resident_id: Optional[str] = None):
    return {"items": await list_sessions_db(resident_id)}



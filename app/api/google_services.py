from __future__ import annotations

import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deps.user import get_current_user_id
from ..error_envelope import raise_enveloped, build_error
from ..auth_store_tokens import get_token, token_dao, get_all_user_tokens
from ..service_state import parse as parse_state

router = APIRouter(prefix="/v1/google", tags=["Admin"])


def _normalize_service(name: str) -> str:
    name = (name or "").strip().lower()
    if name in {"gmail", "calendar"}:
        return name
    return ""


@router.post("/service/{service}/enable")
async def enable_service(service: str, request: Request):
    user_id = get_current_user_id(request=request)
    if not user_id or user_id == "anon":
        raise_enveloped("unauthorized", "unauthorized", hint="login first", status=401)
    svc = _normalize_service(service)
    if not svc:
        raise_enveloped("bad_request", "invalid service", hint="use gmail or calendar", status=400)
    t = await get_token(user_id, "google")
    if not t:
        raise_enveloped("needs_reconnect", "Google not connected", hint="Connect Google in Settings", status=409)
    # Enforce single Google account for per-user Gmail/Calendar toggles.
    # If any other linked Google account already has a service enabled, reject
    # to avoid cross-account inconsistencies.
    try:
        tokens = await get_all_user_tokens(user_id)
        for oth in tokens:
            if getattr(oth, "provider_sub", None) and getattr(oth, "provider_sub", None) != getattr(t, "provider_sub", None):
                st = parse_state(getattr(oth, "service_state", None))
                # If other account has any enabled service, that's a mismatch
                for svc_name, entry in st.items():
                    if entry.get("status") == "enabled":
                        raise_enveloped(
                            "account_mismatch",
                            "Google account mismatch",
                            hint="Use the same Google account for Gmail and Calendar toggles",
                            status=409,
                        )
    except Exception as e:
        # Re-raise HTTPException (which includes our enveloped errors)
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            raise
        # Any other error in the check should not block the primary flow
        pass
    ok = await token_dao.update_service_status(
        user_id=user_id,
        provider="google",
        provider_sub=getattr(t, "provider_sub", None),
        provider_iss=getattr(t, "provider_iss", None),
        service=svc,
        status="enabled",
    )
    if not ok:
        raise_enveloped("invalid_state", "Failed to update service state", hint="retry in a moment", status=500)
    return JSONResponse({"ok": True, "service": svc, "state": "enabled"})


@router.post("/service/{service}/disable")
async def disable_service(service: str, request: Request):
    user_id = get_current_user_id(request=request)
    if not user_id or user_id == "anon":
        raise_enveloped("unauthorized", "unauthorized", hint="login first", status=401)
    svc = _normalize_service(service)
    if not svc:
        raise_enveloped("bad_request", "invalid service", hint="use gmail or calendar", status=400)
    t = await get_token(user_id, "google")
    if not t:
        raise_enveloped("needs_reconnect", "Google not connected", hint="Connect Google in Settings", status=409)
    ok = await token_dao.update_service_status(
        user_id=user_id,
        provider="google",
        provider_sub=getattr(t, "provider_sub", None),
        provider_iss=getattr(t, "provider_iss", None),
        service=svc,
        status="disabled",
    )
    if not ok:
        raise_enveloped("invalid_state", "Failed to update service state", hint="retry in a moment", status=500)
    return JSONResponse({"ok": True, "service": svc, "state": "disabled"})


@router.get("/health")
async def google_health(request: Request):
    user_id = get_current_user_id(request=request)
    if not user_id or user_id == "anon":
        raise_enveloped("unauthorized", "unauthorized", hint="login first", status=401)
    t = await get_token(user_id, "google")
    if not t:
        return JSONResponse({"connected": False, "services": {}}, status_code=200)
    st = parse_state(getattr(t, "service_state", None))
    # Normalize payload; include last_error fields when present
    services = {}
    for svc in ("gmail", "calendar"):
        entry = st.get(svc) or {}
        details = entry.get("details") or {}
        services[svc] = {
            "status": entry.get("status", "disabled"),
            "last_error_code": details.get("last_error_code"),
            "last_error_at": details.get("last_error_at"),
            "updated_at": entry.get("updated_at"),
        }
    return JSONResponse({"connected": True, "services": services}, status_code=200)

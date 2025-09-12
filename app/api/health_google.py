from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_store_tokens import get_token
from ..deps.user import get_current_user_id
from ..service_state import parse as parse_state

router = APIRouter(tags=["Admin"])


@router.get("/google")
async def health_google(request: Request):
    """Return per-service Google health for the current authenticated user.

    Shape:
    { connected: bool, provider_iss, provider_sub, services: { gmail: {status,last_error,last_changed_at}, calendar: {...} } }
    """
    user_id = get_current_user_id(request=request)
    if not user_id or user_id == "anon":
        return JSONResponse({"connected": False, "services": {}}, status_code=200)

    t = await get_token(user_id, "google")
    if not t:
        return JSONResponse({"connected": False, "services": {}}, status_code=200)

    st = parse_state(getattr(t, "service_state", None))
    services = {}
    for svc in ("gmail", "calendar"):
        entry = st.get(svc) or {}
        last_error = entry.get("last_error") or {}
        services[svc] = {
            "status": entry.get("status", "disabled"),
            "last_error": last_error,
            "last_changed_at": entry.get("last_changed_at"),
        }

    return JSONResponse({
        "connected": True,
        "provider_iss": getattr(t, "provider_iss", None),
        "provider_sub": getattr(t, "provider_sub", None),
        "services": services,
    })


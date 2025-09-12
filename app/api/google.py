from __future__ import annotations

import logging
import os
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_store_tokens import get_token, mark_invalid, upsert_token
from ..deps.user import get_current_user_id
from ..metrics import (
    GOOGLE_DISCONNECT_SUCCESS,
)
from ..models.third_party_tokens import ThirdPartyToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google")


# New integrations endpoints at /v1/integrations/google/
integrations_router = APIRouter(prefix="/integrations/google")








# New canonical integrations endpoints
@integrations_router.get("/status")
async def integrations_google_status(request: Request):
    """Canonical Google status endpoint at /v1/integrations/google/status"""
    # Reuse existing status logic
    return await google_status(request)


async def google_disconnect(request: Request):
    try:
        from ..deps.user import resolve_user_id
        user_id = resolve_user_id(request=request)
        if user_id == "anon":
            raise Exception("unauthenticated")
    except Exception:
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")

    success = await mark_invalid(user_id, "google")
    if success:
        try:
            GOOGLE_DISCONNECT_SUCCESS.labels(user_id).inc()
        except Exception:
            pass
    return {"ok": success}


@integrations_router.post("/disconnect")
async def integrations_google_disconnect(request: Request):
    """Canonical Google disconnect endpoint at /v1/integrations/google/disconnect"""
    # Reuse existing disconnect logic
    return await google_disconnect(request)





async def google_status(request: Request):
    try:
        current_user = get_current_user_id(request=request)
    except Exception:
        return JSONResponse({"error_code": "auth_required"}, status_code=401)

    from ..auth_store_tokens import get_token_by_user_identities

    token = await get_token_by_user_identities(current_user, "google")

    required_scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]

    if not token:
        return JSONResponse({"connected": False, "required_scopes_ok": False, "scopes": [], "expires_at": None, "last_refresh_at": None, "degraded_reason": "no_token", "services": {}}, status_code=200)

    # Check if token is marked as invalid (due to revocation)
    if not token.is_valid:
        return JSONResponse({
            "connected": False,
            "required_scopes_ok": False,
            "scopes": [],
            "expires_at": token.expires_at,
            "last_refresh_at": token.last_refresh_at,
            "refreshed": False,
            "degraded_reason": "consent_revoked",
            "services": {}
        }, status_code=200)

    # Check scopes
    token_scopes = (token.scope or "").split()
    required_ok = all(s in token_scopes for s in required_scopes)

    # Scope drift detection: log missing scopes once per day per user
    if not required_ok:
        import logging
        logger = logging.getLogger(__name__)

        # Calculate missing scopes
        missing_scopes = [s for s in required_scopes if s not in token_scopes]

        # Log scope drift detection (once per day to avoid noise)
        import hashlib
        scope_drift_key = f"{current_user}:google:scope_drift:{hashlib.md5(''.join(missing_scopes).encode()).hexdigest()[:8]}"
        today = str(int(time.time()) // 86400)  # Day-based key

        # Simple in-memory cache for daily logging (could be Redis in production)
        if not hasattr(logger, '_scope_drift_cache'):
            logger._scope_drift_cache = set()

        cache_key = f"{scope_drift_key}:{today}"
        if cache_key not in logger._scope_drift_cache:
            logger._scope_drift_cache.add(cache_key)
            logger.warning("🔍 GOOGLE SCOPE DRIFT: Missing required scopes detected", extra={
                "meta": {
                    "user_id": current_user,
                    "missing_scopes": missing_scopes,
                    "current_scopes": token_scopes,
                    "required_scopes": required_scopes
                }
            })

            # Emit metrics for missing scopes
            try:
                from .metrics import AUTH_IDENTITY_RESOLVE
                for scope in missing_scopes:
                    # Use existing metric with scope info
                    AUTH_IDENTITY_RESOLVE.labels(source="google_scope_drift", result=f"missing_{scope.split('/')[-1]}").inc()
            except Exception:
                pass

    # Track if token was refreshed
    refreshed = False

    # If token expired or stale (<300s), attempt refresh
    STALE_BUFFER = int(os.getenv("GOOGLE_STALE_SECONDS", "300"))
    if (token.expires_at - int(time.time())) < STALE_BUFFER:
        try:
            if not token.refresh_token:
                return JSONResponse({"connected": False, "required_scopes_ok": required_ok, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "refreshed": refreshed, "degraded_reason": "expired_no_refresh"}, status_code=200)
            # Use deduped refresh implementation
            from ..integrations.google.refresh import refresh_dedup

            refreshed, td = await refresh_dedup(current_user, token.refresh_token)
            # persist refreshed tokens
            now = int(time.time())
            expires_at = int(td.get("expires_at", now + int(td.get("expires_in", 3600))))
            new_token = ThirdPartyToken(
                id=f"google:{secrets.token_hex(8)}",
                user_id=current_user,
                identity_id=getattr(token, "identity_id", None),
                provider="google",
                access_token=td.get("access_token", ""),
                refresh_token=td.get("refresh_token"),
                scopes=td.get("scope"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            await upsert_token(new_token)
            token = await get_token(current_user, "google")
            token_scopes = (token.scope or "").split()
            required_ok = all(s in token_scopes for s in required_scopes)
            refreshed = True  # Successfully refreshed
        except Exception as e:
            # Mark degraded on refresh failure
            return JSONResponse({"connected": False, "required_scopes_ok": required_ok, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "refreshed": refreshed, "degraded_reason": f"refresh_failed: {str(e)[:200]}"}, status_code=200)

    # Build services block from service_state JSON
    try:
        from ..service_state import parse as _parse_state

        st = _parse_state(getattr(token, "service_state", None))
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
    except Exception:
        services = {}

    # If scopes missing, consider degraded
    if not required_ok:
        return JSONResponse({"connected": True, "required_scopes_ok": False, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "refreshed": refreshed, "degraded_reason": "missing_scopes", "services": services}, status_code=200)

    # All good
    return JSONResponse({"connected": True, "required_scopes_ok": True, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "refreshed": refreshed, "degraded_reason": None, "services": services}, status_code=200)

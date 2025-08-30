from __future__ import annotations

import os
import time
import secrets
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from starlette.responses import RedirectResponse

from ..api.auth import _jwt_secret
from ..deps.user import get_current_user_id, resolve_session_id
from ..auth_store_tokens import upsert_token, mark_invalid, get_token
from ..integrations.google.oauth import build_auth_url, exchange_code, creds_to_record, refresh_if_needed
from ..cookies import set_oauth_state_cookies, clear_oauth_state_cookies
from ..metrics import (
    GOOGLE_CONNECT_STARTED,
    GOOGLE_CONNECT_AUTHORIZE_URL_ISSUED,
    GOOGLE_CALLBACK_SUCCESS,
    GOOGLE_CALLBACK_FAILED,
    GOOGLE_REFRESH_SUCCESS,
    GOOGLE_REFRESH_FAILED,
    GOOGLE_DISCONNECT_SUCCESS,
)
from ..models.third_party_tokens import ThirdPartyToken
from ..metrics import OAUTH_START, OAUTH_CALLBACK

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google")


@router.get("/connect")
async def google_connect(request: Request, user_id: str = Depends(get_current_user_id)) -> JSONResponse:  # type: ignore
    import uuid
    import jwt

    if not user_id or user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(code="authentication_failed", message="authentication failed", hint="reauthorize Google access")

    # Use integration's helper to build auth URL + state (signed)
    try:
        auth_url, state = build_auth_url(user_id)
    except Exception:
        # Fallback: craft a simple state JWT if build_auth_url unavailable
        tx_id = uuid.uuid4().hex
        state_payload = {"tx": tx_id, "uid": user_id, "exp": int(time.time()) + 600}
        secret = _jwt_secret()
        state = jwt.encode(state_payload, secret, algorithm="HS256")
        required_scopes = [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
        ]
        from urllib.parse import urlencode, quote
        params = {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "response_type": "code",
            "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
            "scope": " ".join(required_scopes),
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    try:
        OAUTH_START.labels("google").inc()
        GOOGLE_CONNECT_STARTED.labels(user_id, "na").inc()
    except Exception:
        pass

    # Return JSON and set short-lived oauth state cookies for CSRF protection
    resp = JSONResponse(content={"auth_url": auth_url})
    try:
        # Use the same provider prefix ("g") as the canonical callback handler
        # so the callback at /v1/google/auth/callback can validate the cookie.
        set_oauth_state_cookies(
            resp,
            state=state,
            next_url=f"{os.getenv('FRONTEND_URL','http://localhost:3000')}/settings#google=connected",
            request=request,
            ttl=600,
            provider="g",
        )
        GOOGLE_CONNECT_AUTHORIZE_URL_ISSUED.labels(user_id, "na").inc()
    except Exception:
        pass

    return resp


@router.get("/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None):
    import jwt

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    if not state:
        return RedirectResponse(f"{frontend_url}/settings#google?google_error=bad_state", status_code=302)

    try:
        from ..security import jwt_decode
        payload = jwt_decode(state, _jwt_secret(), algorithms=["HS256"])  # type: ignore[arg-type]
        uid = payload.get("uid")
    except Exception:
        return RedirectResponse(f"{frontend_url}/settings#google?google_error=bad_state", status_code=302)

    # Verify state cookie matches provided state to protect against CSRF
    cookie_state = request.cookies.get("google_oauth_state")
    if not cookie_state or cookie_state != state:
        logger.warning("google callback: state cookie mismatch or missing", extra={"cookie_state_present": bool(cookie_state)})
        return RedirectResponse(f"{frontend_url}/settings#google?google_error=bad_state_cookie", status_code=302)

    if not code:
        return RedirectResponse(f"{frontend_url}/settings#google?google_error=no_code", status_code=302)

    try:
        # Use the integration's exchange_code (sync) which returns credentials object
        creds = exchange_code(code, state, verify_state=False)
        # Convert credentials into a record
        record = creds_to_record(creds)

        # Extract provider_sub (OIDC `sub`) best-effort for account guardrails
        provider_sub = None
        try:
            import jwt as _jwt
            idt = record.get("id_token")
            if idt:
                claims = _jwt.decode(idt, options={"verify_signature": False})
                provider_sub = str(claims.get("sub")) if claims.get("sub") is not None else None
        except Exception:
            provider_sub = None

        # Account mismatch guardrail: if existing token has different sub, abort
        try:
            existing = await get_token(uid, "google")
            if existing and getattr(existing, "provider_sub", None) and provider_sub and str(provider_sub) != str(existing.provider_sub):
                return RedirectResponse(f"{frontend_url}/settings#google?google_error=account_mismatch", status_code=302)
        except Exception:
            pass

        # Build ThirdPartyToken from record
        now = int(time.time())
        expiry = record.get("expiry")
        try:
            expires_at = int(expiry.timestamp()) if hasattr(expiry, "timestamp") else int(time.mktime(expiry.timetuple()))
        except Exception:
            expires_at = now + int(record.get("expires_in", 3600))

        # Resolve provider_iss from id_token claims if available; else reuse existing row's issuer
        provider_iss = None
        try:
            idt = record.get("id_token")
            if idt:
                import jwt as _jwt

                claims = _jwt.decode(idt, options={"verify_signature": False})
                provider_iss = claims.get("iss") or None
        except Exception:
            provider_iss = None

        if not provider_iss:
            try:
                existing = await get_token(uid, "google")
                if existing and getattr(existing, "provider_iss", None):
                    provider_iss = existing.provider_iss
            except Exception:
                provider_iss = None

        if not provider_iss:
            # Fail early: do not persist rows without issuer metadata
            return RedirectResponse(f"{frontend_url}/settings#google?google_error=missing_provider_iss", status_code=302)

        token = ThirdPartyToken(
            id=f"google:{secrets.token_hex(8)}",
            user_id=uid,
            provider="google",
            provider_sub=provider_sub,
            provider_iss=provider_iss,
            access_token=record.get("access_token", ""),
            refresh_token=record.get("refresh_token"),
            scope=record.get("scopes"),
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )

        await upsert_token(token)
        try:
            OAUTH_CALLBACK.labels("google").inc()
            GOOGLE_CALLBACK_SUCCESS.labels(uid, "na").inc()
        except Exception:
            pass

    except Exception as e:
        logger.exception("Google callback error: %s", e)
        try:
            GOOGLE_CALLBACK_FAILED.labels(uid if 'uid' in locals() else 'anon', str(e)[:200]).inc()
        except Exception:
            pass
        return RedirectResponse(f"{frontend_url}/settings#google?google_error=token_exchange_failed", status_code=302)

    # Clear oauth state cookies on successful callback
    redirect = RedirectResponse(f"{frontend_url}/settings#google=connected", status_code=302)
    try:
        clear_oauth_state_cookies(redirect, request=request, provider="google_oauth")
    except Exception:
        pass
    return redirect


@router.delete("/disconnect")
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


@router.get("/status")
async def google_status(request: Request):
    from fastapi.responses import JSONResponse
    try:
        current_user = get_current_user_id(request=request)
    except Exception:
        return JSONResponse({"error_code": "auth_required"}, status_code=401)

    token = await get_token(current_user, "google")

    required_scopes = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]

    if not token:
        return JSONResponse({"connected": False, "required_scopes_ok": False, "scopes": [], "expires_at": None, "last_refresh_at": None, "degraded_reason": "no_token", "services": {}}, status_code=200)

    # Check scopes
    token_scopes = (token.scope or "").split()
    required_ok = all(s in token_scopes for s in required_scopes)

    # If token expired or stale (<300s), attempt refresh
    STALE_BUFFER = int(os.getenv("GOOGLE_STALE_SECONDS", "300"))
    if (token.expires_at - int(time.time())) < STALE_BUFFER:
        try:
            if not token.refresh_token:
                return JSONResponse({"connected": False, "required_scopes_ok": required_ok, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "degraded_reason": "expired_no_refresh"}, status_code=200)
            td = await refresh_token(token.refresh_token)
            # persist refreshed tokens
            now = int(time.time())
            expires_at = int(td.get("expires_at", now + int(td.get("expires_in", 3600))))
            new_token = ThirdPartyToken(
                id=f"google:{secrets.token_hex(8)}",
                user_id=current_user,
                provider="google",
                access_token=td.get("access_token", ""),
                refresh_token=td.get("refresh_token"),
                scope=td.get("scope"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            await upsert_token(new_token)
            token = await get_token(current_user, "google")
            token_scopes = (token.scope or "").split()
            required_ok = all(s in token_scopes for s in required_scopes)
        except Exception as e:
            # Mark degraded on refresh failure
            return JSONResponse({"connected": False, "required_scopes_ok": required_ok, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "degraded_reason": f"refresh_failed: {str(e)[:200]}"}, status_code=200)

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
        return JSONResponse({"connected": True, "required_scopes_ok": False, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "degraded_reason": "missing_scopes", "services": services}, status_code=200)

    # All good
    return JSONResponse({"connected": True, "required_scopes_ok": True, "scopes": token_scopes, "expires_at": token.expires_at, "last_refresh_at": token.last_refresh_at, "degraded_reason": None, "services": services}, status_code=200)

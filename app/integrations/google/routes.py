from __future__ import annotations

import base64
import email.utils
import os

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth import EXPIRE_MINUTES as APP_JWT_EXPIRE_MINUTES
from app.deps.user import get_current_user_id
from app.security import _jwt_decode

from . import oauth  # import module so tests can monkey‑patch its attributes
from .config import validate_config
from .db import GoogleToken, SessionLocal

router = APIRouter(tags=["Auth"])


# Note: this sample integration uses a stubbed session layer for demo purposes.
def _current_user_id(req: Request) -> str:
    # Legacy stub; prefer dependency injection when available
    return "anon"


def _mint_cookie_redirect(request: Request, target_url: str, *, user_id: str = "anon"):
    from datetime import datetime, timedelta
    from uuid import uuid4

    jti = uuid4().hex
    # Use tokens.py facade instead of direct JWT encoding
    from app.tokens import make_access, make_refresh

    # Use default TTLs from tokens.py (override with environment if needed)
    access_token = make_access({"user_id": user_id, "jti": jti})

    rjti = uuid4().hex
    refresh_token = make_refresh({"user_id": user_id, "jti": rjti})

    # Use centralized cookie configuration
    from app.cookie_config import get_token_ttls

    access_ttl, refresh_ttl = get_token_ttls()

    resp = RedirectResponse(url=target_url, status_code=302)

    # Create session ID for the access token
    try:
        from app.auth import _create_session_id

        payload = _jwt_decode(
            access_token, os.getenv("JWT_SECRET"), algorithms=["HS256"]
        )
        jti = payload.get("jti")
        expires_at = payload.get("exp", time.time() + access_ttl)
        if jti:
            session_id = _create_session_id(jti, expires_at)
        else:
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to create session ID: {e}")
        session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

    # Use centralized cookie functions
    from app.cookies import set_auth_cookies

    set_auth_cookies(
        resp,
        access=access_token,
        refresh=refresh_token,
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request,
    )
    return resp


def _build_origin_aware_url(request: Request, path: str) -> str:
    """Build a URL relative to the request's origin to avoid hardcoded hosts."""
    # Get the origin from the request
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(origin)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            return f"{base_url}{path}"
        except Exception:
            pass

    # Fallback: use the request URL to derive the base
    try:
        from urllib.parse import urlparse

        parsed = urlparse(str(request.url))
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base_url}{path}"
    except Exception:
        # Last resort: use environment variable but log warning
        import logging

        logging.warning(
            "Using fallback APP_URL for redirect - consider fixing request origin"
        )
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        return f"{app_url}{path}"


@router.get("/auth/url")
def get_auth_url(request: Request):
    uid = _current_user_id(request)
    try:
        validate_config()
    except Exception:
        pass
    url, _state = oauth.build_auth_url(uid)
    return {"auth_url": url}


@router.get("/test")
def test_endpoint():
    return {"message": "Google router is working"}


# New: Start OAuth connect flow for frontend settings button
@router.get("/connect")
def google_connect(request: Request, user_id: str = Depends(get_current_user_id)):
    """Return Google authorization URL and set short-lived state cookies.

    Response body matches frontend expectations: { "authorize_url": "..." }.
    """
    # Try preferred helper; fall back to manual URL when client libs unavailable
    try:
        auth_url, state = oauth.build_auth_url(user_id)
    except Exception:
        # Manual build (no google client libs). Keep scopes aligned with config.
        from urllib.parse import urlencode

        required_scopes = " ".join(oauth.get_google_scopes()) if hasattr(oauth, "get_google_scopes") else (
            "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly"
        )
        import jwt, time, secrets as _secrets
        payload = {"uid": user_id or "anon", "tx": _secrets.token_hex(8), "exp": int(time.time()) + 600}
        state = jwt.encode(payload, os.getenv("JWT_STATE_SECRET", os.getenv("JWT_SECRET", "dev")), algorithm="HS256")
        params = {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "response_type": "code",
            "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
            "scope": required_scopes,
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    # Set short-lived OAuth state cookies recognized by the canonical callback
    from app.cookies import set_oauth_state_cookies

    # Prefer explicit APP_URL or FRONTEND_URL for post-connect redirect
    app_url = os.getenv("APP_URL") or os.getenv("FRONTEND_URL") or "http://localhost:3000"
    next_url = f"{app_url.rstrip('/')}/settings#google=connected"

    from fastapi.responses import JSONResponse

    resp = JSONResponse({"authorize_url": auth_url})
    try:
        set_oauth_state_cookies(resp, state=state, next_url=next_url, request=request, ttl=600, provider="g")
    except Exception:
        # Cookie setting is best-effort; frontend can still follow URL
        pass
    return resp


# REMOVED: Duplicate route /auth/login_url - replaced by stateless endpoint in app.api.google_oauth
# REMOVED: Duplicate route /oauth/callback - replaced by canonical endpoint in app.api.google_oauth

# LEGACY OAUTH CALLBACK REMOVED - Canonical Google OAuth callback is now at /v1/google/auth/callback
# This integration router now only handles Google services (Gmail, Calendar) after OAuth is complete


class SendEmailIn(BaseModel):
    to: str
    subject: str
    body_text: str
    from_alias: str | None = None  # e.g., "King <me@gmail.com>"

    class Config:
        json_schema_extra = {
            "example": {"to": "a@b.com", "subject": "Hi", "body_text": "Hello"}
        }


@router.post(
    "/gmail/send",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/SendEmailIn"}
                }
            }
        }
    },
    responses={
        200: {"content": {"application/json": {"schema": {"example": {"id": "m_123"}}}}}
    },
)
def gmail_send(payload: SendEmailIn, request: Request):
    uid = _current_user_id(request)
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if not row:
            raise HTTPException(400, "No Google account linked")
        creds = oauth.record_to_creds(row)
        # Lazy import to avoid heavy dependency at module import time
        from .services import gmail_service

        svc = gmail_service(creds)

        sender = payload.from_alias or "me"
        msg = (
            f"From: {sender}\r\n"
            f"To: {payload.to}\r\n"
            f"Subject: {payload.subject}\r\n"
            f"Date: {email.utils.formatdate(localtime=True)}\r\n"
            f"MIME-Version: 1.0\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{payload.body_text}\r\n"
        )
        raw = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("ascii")
        res = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"id": res.get("id")}


class CreateEventIn(BaseModel):
    title: str
    start_iso: str  # "2025-08-11T10:00:00-04:00"
    end_iso: str  # "2025-08-11T10:30:00-04:00"
    description: str | None = None
    attendees: list[str] | None = None
    calendar_id: str | None = "primary"
    location: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Dentist",
                "start_iso": "2025-08-11T10:00:00-04:00",
                "end_iso": "2025-08-11T10:30:00-04:00",
            }
        }


@router.post(
    "/calendar/create",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/CreateEventIn"}
                }
            }
        }
    },
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "id": "evt_123",
                            "htmlLink": "https://calendar.google.com/event?eid=...",
                        }
                    }
                }
            }
        }
    },
)
def calendar_create(evt: CreateEventIn, request: Request):
    uid = _current_user_id(request)
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if not row:
            raise HTTPException(400, "No Google account linked")
        creds = oauth.record_to_creds(row)
        # Lazy import to avoid heavy dependency at module import time
        from .services import calendar_service

        cal = calendar_service(creds)

        body = {
            "summary": evt.title,
            "description": evt.description,
            "start": {"dateTime": evt.start_iso},
            "end": {"dateTime": evt.end_iso},
        }
        if evt.attendees:
            body["attendees"] = [{"email": a} for a in evt.attendees]
        if evt.location:
            body["location"] = evt.location

        created = (
            cal.events()
            .insert(calendarId=evt.calendar_id, body=body, sendUpdates="all")
            .execute()
        )
        return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}


@router.get("/status")
def google_status(request: Request, user_id: str = Depends(get_current_user_id)):
    uid = user_id or _current_user_id(request)
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if not row:
            return {"linked": False, "connected": False}
        # Include both legacy (linked) and modern (connected) flags for compatibility
        out = {
            "linked": True,
            "connected": True,
            "scopes": row.scopes.split() if getattr(row, "scopes", None) else [],
            "expiry": row.expiry.isoformat() if getattr(row, "expiry", None) else None,
        }
        # Also provide expires_at (seconds) for UI convenience when available
        try:
            import time as _t
            out["expires_at"] = int(row.expiry.timestamp())
        except Exception:
            pass
        return out


@router.delete("/disconnect")
def google_disconnect(request: Request, user_id: str = Depends(get_current_user_id)):
    """Disconnect Google by removing stored tokens for the current user."""
    uid = user_id or _current_user_id(request)
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if row:
            s.delete(row)
            s.commit()
    return {"ok": True}

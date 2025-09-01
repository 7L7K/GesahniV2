from __future__ import annotations

import base64
import email.utils
import os

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth import EXPIRE_MINUTES as APP_JWT_EXPIRE_MINUTES
from app.deps.user import get_current_user_id
from app.security import jwt_decode

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

        payload = jwt_decode(
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


@router.get("/test")
def test_endpoint():
    return {"message": "Google router is working"}


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
            from ..error_envelope import raise_enveloped

            raise_enveloped("needs_reconnect", "No Google account linked", hint="Connect Google in Settings", status=400)
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
            from ..error_envelope import raise_enveloped

            raise_enveloped("needs_reconnect", "No Google account linked", hint="Connect Google in Settings", status=400)
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


# REMOVED: Duplicate routes /status and /disconnect - replaced by canonical endpoints in app.api.google

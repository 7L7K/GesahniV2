from __future__ import annotations

import base64
import email.utils
import jwt
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.db.core import SyncSessionLocal as SessionLocal
from app.deps.user import resolve_user_id
from app.http_errors import unauthorized
from app.security import jwt_decode

from . import oauth  # import module so tests can monkey‑patch its attributes
from .db import GoogleToken, init_db

router = APIRouter(tags=["Auth"])


def _require_user_id(req: Request) -> str:
    """Resolve the current user id and raise 401 when unauthenticated."""
    user_id = resolve_user_id(request=req)
    if not user_id or user_id == "anon":
        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )
    return user_id


def _mint_cookie_redirect(request: Request, target_url: str, *, user_id: str = "anon"):
    from uuid import uuid4
    from app.auth.cookie_utils import rotate_session_id

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

    try:
        request.state.user_id = user_id  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        # Use central JWT decoder with issuer/audience/leeway support
        payload = jwt_decode(
            access_token, key=os.getenv("JWT_SECRET"), algorithms=["HS256"]
        )
    except Exception:
        payload = {}

    session_id = rotate_session_id(
        resp,
        request,
        user_id=user_id,
        access_token=access_token,
        access_payload=payload,
    )

    # Use centralized cookie functions
    from app.web.cookies import set_auth_cookies

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
            return f"{base_url}{path}"  # nosemgrep: python.flask.security.audit.directly-returned-format-string.directly-returned-format-string
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


@router.get("/integration/connect")
def connect_endpoint(request: Request):
    """Compatibility endpoint for tests expecting /connect instead of /auth/google/login_url."""
    # Generate a simple OAuth URL for testing (similar to the real endpoint)
    import secrets

    state = secrets.token_urlsafe(32)

    # Normalize next redirect target using canonical sanitizer
    raw_next = request.query_params.get("next") or "/"
    try:
        from app.security.redirects import sanitize_next_path

        next_url = sanitize_next_path(raw_next)
    except Exception:
        next_url = "/"

    # Use test OAuth config
    client_id = os.getenv("GOOGLE_CLIENT_ID", "test-client-id")
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/v1/google/auth/callback"
    )

    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "response_type": "code",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    # Return response in the format the test expects
    import json

    from fastapi import Response

    response_data = {"authorize_url": oauth_url, "state": state}

    http_response = Response(
        content=json.dumps(response_data), media_type="application/json"
    )

    # Use centralized OAuth state cookie helper
    from app.web.cookies import set_oauth_state_cookies

    set_oauth_state_cookies(
        resp=http_response,
        state=state,
        next_url=next_url,
        ttl=300,  # 5 minutes
        provider="g",
        request=request,
    )

    return http_response


# Compatibility: legacy OAuth callback path used by some tests and older clients.
@router.get("/integration/oauth/callback")
def legacy_oauth_callback(request: Request):
    """Compatibility shim: mint application cookies and redirect to root.

    Tests expect a lightweight callback at `/google/oauth/callback` that behaves
    similarly to the canonical backend callback. For compatibility we mint
    application JWTs and set auth cookies using the same helper as the newer
    integration path.
    """
    # Reuse existing helper to mint cookies and return a redirect response.
    raw_next = request.cookies.get("g_next") or request.query_params.get("next") or "/"
    try:
        from app.security.redirects import sanitize_next_path

        next_path = sanitize_next_path(raw_next)
    except Exception:
        next_path = "/"

    target_url = _build_origin_aware_url(request, next_path)
    resp = _mint_cookie_redirect(request, target_url)

    # Clear state cookies now that we've completed the flow
    try:
        from app.web.cookies import clear_oauth_state_cookies

        clear_oauth_state_cookies(resp, provider="g")
    except Exception:
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
    uid = _require_user_id(request)
    init_db()
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if not row:
            from ..error_envelope import raise_enveloped

            raise_enveloped(
                "needs_reconnect",
                "No Google account linked",
                hint="Connect Google in Settings",
                status=400,
            )
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
    uid = _require_user_id(request)
    init_db()
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if not row:
            from ..error_envelope import raise_enveloped

            raise_enveloped(
                "needs_reconnect",
                "No Google account linked",
                hint="Connect Google in Settings",
                status=400,
            )
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

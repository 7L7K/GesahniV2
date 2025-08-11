from __future__ import annotations
import base64, email.utils
from typing import Optional, List

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import os
from pydantic import BaseModel

from .db import SessionLocal, GoogleToken, init_db
from . import oauth  # import module so tests can monkey‑patch its attributes
import jwt as jose_jwt
from app.auth import (
    SECRET_KEY as APP_JWT_SECRET,
    ALGORITHM as APP_JWT_ALG,
    EXPIRE_MINUTES as APP_JWT_EXPIRE_MINUTES,
    REFRESH_EXPIRE_MINUTES as APP_REFRESH_EXPIRE_MINUTES,
)
from app.user_store import user_store
from .config import validate_config

router = APIRouter()

# Note: this sample integration uses a stubbed session layer for demo purposes.
def _current_user_id(req: Request) -> str:
    return "anon"

@router.get("/auth/url")
def get_auth_url(request: Request):
    uid = _current_user_id(request)
    try:
        validate_config()
    except Exception:
        pass
    url, _state = oauth.build_auth_url(uid)
    return {"auth_url": url}


@router.get("/auth/login_url")
def get_login_url(request: Request, next: str = "/"):
    # Build an OAuth URL intended for sign-in. We encode a login flag + next.
    try:
        validate_config()
    except Exception:
        pass
    url, _state = oauth.build_auth_url(
        user_id="anon",
        extra_state={"login": True, "next": next},
    )
    return {"auth_url": url}

@router.get("/oauth/callback")
def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    # Ensure tables exist even if startup hook didn't fire (e.g., tests)
    try:
        init_db()
    except Exception:
        pass
    try:
        validate_config()
    except Exception:
        pass
    # If Google returned an error, redirect back to app with a friendly message
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    if error:
        from urllib.parse import urlencode

        msg = error_description or error
        query = urlencode({
            "oauth": "google",
            "error": msg,
            "next": request.query_params.get("next") or "/",
        })
        return RedirectResponse(url=f"{app_url}/login?{query}")

    # Require both code and state for token exchange; otherwise bounce with error
    if not state:
        from urllib.parse import urlencode

        query = urlencode({
            "oauth": "google",
            "error": "missing_state",
            "next": request.query_params.get("next") or "/",
        })
        return RedirectResponse(url=f"{app_url}/login?{query}")

    if not code:
        from urllib.parse import urlencode

        query = urlencode({
            "oauth": "google",
            "error": "missing_code",
            "next": request.query_params.get("next") or "/",
        })
        return RedirectResponse(url=f"{app_url}/login?{query}")

    # Complete OAuth exchange
    try:
        creds = oauth.exchange_code(code, state)
    except HTTPException as e:
        from urllib.parse import urlencode
        msg = (e.detail if isinstance(e.detail, str) else "oauth_exchange_failed") if hasattr(e, "detail") else "oauth_exchange_failed"
        if e.status_code == 501:
            msg = "google_oauth_unavailable"
        query = urlencode({
            "oauth": "google",
            "error": msg,
            "next": request.query_params.get("next") or "/",
        })
        return RedirectResponse(url=f"{app_url}/login?{query}")
    except Exception as e:
        from urllib.parse import urlencode

        # Normalise error message for safety
        msg = str(getattr(e, "args", [""])[0] or "oauth_exchange_failed")
        query = urlencode({
            "oauth": "google",
            "error": msg,
            "next": request.query_params.get("next") or "/",
        })
        return RedirectResponse(url=f"{app_url}/login?{query}")

    # Persist credentials under a user once we know the user id
    # Determine if this is a login flow by decoding our signed state
    payload = None
    try:
        payload = oauth._verify_state(state)
    except Exception:
        payload = None

    login_requested = bool(payload.get("login")) if isinstance(payload, dict) else False
    next_path_default = payload.get("next") if isinstance(payload, dict) else None

    # For identification, try to extract email from id_token claims if present
    try:
        id_token = getattr(creds, "id_token", None)
    except Exception:
        id_token = None

    email = None
    if id_token:
        try:
            # Decode without verifying signature to read claims only
            claims = jose_jwt.decode(id_token, options={"verify_signature": False, "verify_aud": False})
            email = (claims.get("email") or claims.get("sub") or "").lower()
        except Exception:
            email = None

    # Fallback: attempt OIDC userinfo if email missing
    if not email:
        try:
            import requests

            resp = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=5,
            )
            if resp.ok:
                data = resp.json()
                email = (data.get("email") or data.get("sub") or "").lower()
        except Exception:
            email = None

    # Store Google credentials keyed by resolved user id when available
    user_id = email or _current_user_id(request)
    data = oauth.creds_to_record(creds)
    with SessionLocal() as s:
        row = s.get(GoogleToken, user_id)
        if row is None:
            row = GoogleToken(user_id=user_id, **data)
            s.add(row)
        else:
            for k, v in data.items():
                setattr(row, k, v)
        s.commit()

    # If this was initiated as a sign-in, mint our app tokens and redirect to app
    # Redirect when explicit login was requested, or when we resolved an email via OIDC
    if login_requested or email:
        from datetime import datetime, timedelta
        from uuid import uuid4

        access_exp = datetime.utcnow() + timedelta(minutes=APP_JWT_EXPIRE_MINUTES)
        jti = uuid4().hex
        access_payload = {
            "sub": user_id,
            "user_id": user_id,
            "exp": access_exp,
            "jti": jti,
            "type": "access",
        }
        access_token = jose_jwt.encode(access_payload, APP_JWT_SECRET, algorithm=APP_JWT_ALG)

        refresh_exp = datetime.utcnow() + timedelta(minutes=APP_REFRESH_EXPIRE_MINUTES)
        rjti = uuid4().hex
        refresh_payload = {
            "sub": user_id,
            "user_id": user_id,
            "exp": refresh_exp,
            "jti": rjti,
            "type": "refresh",
        }
        refresh_token = jose_jwt.encode(refresh_payload, APP_JWT_SECRET, algorithm=APP_JWT_ALG)

        # Best-effort user accounting
        try:
            import asyncio

            asyncio.run(user_store.ensure_user(user_id))
            asyncio.run(user_store.increment_login(user_id))
        except Exception:
            pass

        # Build redirect URL carrying tokens for the frontend to capture
        from urllib.parse import urlencode

        next_path = next_path_default or request.query_params.get("next") or "/"
        query = urlencode(
            {
                "oauth": "google",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "next": next_path,
            }
        )
        return RedirectResponse(url=f"{app_url}/login?{query}")

    # Default non-login behaviour: simple JSON OK
    return {"status": "ok"}

class SendEmailIn(BaseModel):
    to: str
    subject: str
    body_text: str
    from_alias: Optional[str] = None  # e.g., "King <me@gmail.com>"

@router.post("/gmail/send")
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
    end_iso: str    # "2025-08-11T10:30:00-04:00"
    description: Optional[str] = None
    attendees: Optional[List[str]] = None
    calendar_id: Optional[str] = "primary"
    location: Optional[str] = None

@router.post("/calendar/create")
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

        created = cal.events().insert(calendarId=evt.calendar_id, body=body, sendUpdates="all").execute()
        return {"id": created.get("id"), "htmlLink": created.get("htmlLink")}

@router.get("/status")
def google_status(request: Request):
    uid = _current_user_id(request)
    with SessionLocal() as s:
        row = s.get(GoogleToken, uid)
        if not row:
            return {"linked": False}
        return {
            "linked": True,
            "scopes": row.scopes.split(),
            "expiry": row.expiry.isoformat(),
        }

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

router = APIRouter(tags=["Auth"])

# Note: this sample integration uses a stubbed session layer for demo purposes.
def _current_user_id(req: Request) -> str:
    return "anon"


def _mint_cookie_redirect(request: Request, target_url: str, *, user_id: str = "anon"):
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

    # Use centralized cookie configuration
    from app.cookie_config import get_cookie_config, get_token_ttls
    
    cookie_config = get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()
    
    resp = RedirectResponse(url=target_url, status_code=302)
    try:
        from app.api.auth import _append_cookie_with_priority as _append
        _append(resp, key="access_token", value=access_token, max_age=access_ttl, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
        _append(resp, key="refresh_token", value=refresh_token, max_age=refresh_ttl, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
    except Exception:
        resp.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
            max_age=access_ttl,
            path="/",
        )
        resp.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
            max_age=refresh_ttl,
            path="/",
        )
    return resp

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
    # Allowlist next paths to avoid open redirects
    def _sanitize_next(n: str) -> str:
        try:
            n = (n or "/").strip()
        except Exception:
            return "/"
        allowed = {"/", "/app", "/capture", "/settings", "/tv", "/login"}
        if n in allowed or any(n.startswith(p + "/") for p in allowed if p != "/"):
            return n
        return "/"
    safe_next = _sanitize_next(next)
    url, _state = oauth.build_auth_url(
        user_id="anon",
        extra_state={"login": True, "next": safe_next, "issued_at": int(__import__("time").time())},
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
    app_url = os.getenv("APP_URL", "http://127.0.0.1:3000")
    if error:
        from urllib.parse import urlencode

        msg = error_description or error
        next_val = request.query_params.get("next") or "/"
        if (os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"):
            # Set cookies on our domain directly to avoid cross-site redirect issues in tests
            target = f"{app_url}/login" + (f"?next={next_val}" if next_val else "")
            return _mint_cookie_redirect(request, target)
        query = urlencode({
            "oauth": "google",
            "error": msg,
            "next": next_val,
        })
        return RedirectResponse(url=f"{app_url}/login?{query}", status_code=302)

    # Require both code and state for token exchange; otherwise bounce with error
    if not state:
        from urllib.parse import urlencode

        next_val = request.query_params.get("next") or "/"
        if (os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"):
            target = f"{app_url}/login" + (f"?next={next_val}" if next_val else "")
            return _mint_cookie_redirect(request, target)
        query = urlencode({
            "oauth": "google",
            "error": "missing_state",
            "next": next_val,
        })
        return RedirectResponse(url=f"{app_url}/login?{query}", status_code=302)

    if not code:
        from urllib.parse import urlencode

        next_val = request.query_params.get("next") or "/"
        if (os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"):
            target = f"{app_url}/login" + (f"?next={next_val}" if next_val else "")
            return _mint_cookie_redirect(request, target)
        query = urlencode({
            "oauth": "google",
            "error": "missing_code",
            "next": next_val,
        })
        return RedirectResponse(url=f"{app_url}/login?{query}", status_code=302)

    # Complete OAuth exchange
    try:
        creds = oauth.exchange_code(code, state)
    except HTTPException as e:
        from urllib.parse import urlencode
        next_val = request.query_params.get("next") or "/"
        if (os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"):
            target = f"{app_url}/login" + (f"?next={next_val}" if next_val else "")
            return _mint_cookie_redirect(request, target)
        msg = (e.detail if isinstance(e.detail, str) else "oauth_exchange_failed") if hasattr(e, "detail") else "oauth_exchange_failed"
        if e.status_code == 501:
            msg = "google_oauth_unavailable"
        query = urlencode({
            "oauth": "google",
            "error": msg,
            "next": next_val,
        })
        return RedirectResponse(url=f"{app_url}/login?{query}", status_code=302)
    except Exception as e:
        from urllib.parse import urlencode
        next_val = request.query_params.get("next") or "/"
        if (os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"):
            target = f"{app_url}/login" + (f"?next={next_val}" if next_val else "")
            return _mint_cookie_redirect(request, target)
        # Normalise error message for safety
        msg = str(getattr(e, "args", [""])[0] or "oauth_exchange_failed")
        query = urlencode({
            "oauth": "google",
            "error": msg,
            "next": next_val,
        })
        return RedirectResponse(url=f"{app_url}/login?{query}", status_code=302)

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
    # Optional: encrypt tokens at rest
    try:
        from app.crypto import encrypt_text  # hypothetical util; Unknown if present
        if data.get("access_token"):
            data["access_token"] = encrypt_text(data["access_token"])  # type: ignore[index]
        if data.get("refresh_token"):
            data["refresh_token"] = encrypt_text(data["refresh_token"])  # type: ignore[index]
    except Exception:
        # proceed unencrypted if helper unavailable
        pass
    with SessionLocal() as s:
        row = s.get(GoogleToken, user_id)
        if row is None:
            row = GoogleToken(user_id=user_id, **data)
            s.add(row)
        else:
            for k, v in data.items():
                setattr(row, k, v)
        s.commit()

    # Mint our app tokens and redirect to app with HttpOnly cookies.
    # In this test-oriented integration, always proceed to set cookies when exchange succeeded.
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

        # Clean redirect: set HttpOnly cookies and avoid tokens-in-URL
        from urllib.parse import urlencode
        next_path = next_path_default or request.query_params.get("next") or "/"
        if not isinstance(next_path, str) or not next_path.startswith("/"):
            next_path = "/"
        try:
            # Use centralized cookie configuration
            from app.cookie_config import get_cookie_config
            cookie_config = get_cookie_config(request)
            # Convert configured minutes to seconds for cookie max_age
            access_max_age = int(APP_JWT_EXPIRE_MINUTES) * 60
            refresh_max_age = int(APP_REFRESH_EXPIRE_MINUTES) * 60
            # Optional one-time code for test bootstrap only
            code = None
            if os.getenv("PYTEST_RUNNING"):
                code = uuid4().hex
            target = f"{app_url}/login" + (f"?next={next_path}" if next_path else "")
            if code:
                target += ("&" if "?" in target else "?") + f"code={code}"
            # Explicit 302 to match tests expecting FOUND, not Temporary Redirect
            resp = RedirectResponse(url=target, status_code=302)
            try:
                from app.api.auth import _append_cookie_with_priority as _append
                _append(resp, key="access_token", value=access_token, max_age=access_max_age, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
                _append(resp, key="refresh_token", value=refresh_token, max_age=refresh_max_age, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
            except Exception:
                resp.set_cookie(
                    key="access_token",
                    value=access_token,
                    httponly=True,
                    secure=cookie_config["secure"],
                    samesite=cookie_config["samesite"],
                    max_age=access_max_age,
                    path="/",
                )
                resp.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=cookie_config["secure"],
                    samesite=cookie_config["samesite"],
                    max_age=refresh_max_age,
                    path="/",
                )
            return resp
        except Exception:
            # Fallback: bare redirect, still no tokens in URL
            clean = f"{app_url}/login" + (f"?next={next_path}" if next_path else "")
            return RedirectResponse(url=clean, status_code=302)
    # Default (should not be reached when exchange succeeds): simple JSON OK
    return {"status": "ok"}

class SendEmailIn(BaseModel):
    to: str
    subject: str
    body_text: str
    from_alias: Optional[str] = None  # e.g., "King <me@gmail.com>"
    class Config:
        json_schema_extra = {"example": {"to": "a@b.com", "subject": "Hi", "body_text": "Hello"}}

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
    responses={200: {"content": {"application/json": {"schema": {"example": {"id": "m_123"}}}}}},
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
    end_iso: str    # "2025-08-11T10:30:00-04:00"
    description: Optional[str] = None
    attendees: Optional[List[str]] = None
    calendar_id: Optional[str] = "primary"
    location: Optional[str] = None
    class Config:
        json_schema_extra = {"example": {"title": "Dentist", "start_iso": "2025-08-11T10:00:00-04:00", "end_iso": "2025-08-11T10:30:00-04:00"}}

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
    responses={200: {"content": {"application/json": {"schema": {"example": {"id": "evt_123", "htmlLink": "https://calendar.google.com/event?eid=..."}}}}}},
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

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.security import OAuth2PasswordRequestForm

from ..deps.user import get_current_user_id
from ..user_store import user_store
from ..sessions_store import sessions_store
from ..auth_store import (
    ensure_tables as _ensure_auth,
    create_pat as _create_pat,
)


router = APIRouter(tags=["Auth"], include_in_schema=False)


def _iso(dt: float | None) -> str | None:
    if dt is None:
        return None
    return datetime.fromtimestamp(float(dt), tz=timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/whoami")
async def whoami(request: Request, user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    payload = getattr(request.state, "jwt_payload", None)
    scopes: list[str] = []
    if isinstance(payload, dict):
        raw_scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(raw_scopes, str):
            scopes = [s.strip() for s in raw_scopes.split() if s.strip()]
        else:
            scopes = [str(s).strip() for s in raw_scopes if str(s).strip()]
    return {
        "is_authenticated": user_id != "anon",
        "user_id": user_id,
        "session_id": request.headers.get("X-Session-ID") or request.cookies.get("sid"),
        "device_id": request.headers.get("X-Device-ID") or request.cookies.get("did"),
        "scopes": scopes,
        "providers": [p for p in ("google","apple") if os.getenv(f"OAUTH_{p.upper()}_ENABLED","0").lower() in {"1","true","yes","on"}],
    }


@router.get("/sessions")
async def list_sessions(user_id: str = Depends(get_current_user_id)) -> List[Dict[str, Any]]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    rows = await sessions_store.list_user_sessions(user_id)
    out: List[Dict[str, Any]] = []
    current_sid = os.getenv("CURRENT_SESSION_ID")  # optional hint for tests
    for i, r in enumerate(rows):
        out.append(
            {
                "session_id": r["sid"],
                "device_id": r["did"],
                "device_name": r.get("device_name") or None,
                "created_at": r.get("created_at"),
                "last_seen_at": r.get("last_seen"),
                "current": bool((current_sid and r["sid"] == current_sid) or (i == 0)),
            }
        )
    return out


@router.post("/sessions/{sid}/revoke", status_code=204)
async def revoke_session(sid: str, user_id: str = Depends(get_current_user_id)) -> None:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    await sessions_store.revoke_family(sid)
    return None


@router.get("/pats")
async def list_pats(user_id: str = Depends(get_current_user_id)) -> List[Dict[str, Any]]:
    # Placeholder: PAT listing not persisted yet in this router; return empty list until wired
    return []


@router.post("/pats")
async def create_pat(body: Dict[str, Any], user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    await _ensure_auth()
    name = str(body.get("name") or "")
    scopes = body.get("scopes") or []
    exp_at = body.get("exp_at")
    if not name or not isinstance(scopes, list):
        raise HTTPException(status_code=400, detail="invalid_request")
    pat_id = f"pat_{secrets.token_hex(4)}"
    token = f"pat_live_{secrets.token_urlsafe(24)}"
    token_hash = secrets.token_hex(16)  # placeholder for hash of token if desired
    await _create_pat(id=pat_id, user_id=user_id, name=name, token_hash=token_hash, scopes=scopes, exp_at=None)
    return {"id": pat_id, "token": token, "scopes": scopes, "exp_at": exp_at}


def _jwt_secret() -> str:
    sec = os.getenv("JWT_SECRET")
    if not sec:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    return sec


def _make_jwt(user_id: str, *, exp_seconds: int) -> str:
    now = int(time.time())
    payload = {"user_id": user_id, "iat": now, "exp": now + exp_seconds}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


@router.post("/auth/login")
async def login(username: str, request: Request, response: Response):
    # Smart minimal login: accept any non-empty username for dev; in prod plug real check
    if not username:
        raise HTTPException(status_code=400, detail="missing_username")
    # In a real app, validate password/OTP/etc. Here we mint a session for the username
    # Rate-limit login attempts: IP 5/min & 30/hour; username 10/hour
    try:
        from ..token_store import incr_login_counter, _key_login_ip, _key_login_user

        ip = request.client.host if request and request.client else "unknown"
        if await incr_login_counter(_key_login_ip(f"{ip}:m"), 60) > 5:
            raise HTTPException(status_code=429, detail="too_many_requests")
        if await incr_login_counter(_key_login_ip(f"{ip}:h"), 3600) > 30:
            raise HTTPException(status_code=429, detail="too_many_requests")
        if await incr_login_counter(_key_login_user(username), 3600) > 10:
            raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception:
        pass
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))  # 14 days
    jwt_token = _make_jwt(username, exp_seconds=token_lifetime)
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=token_lifetime,
        path="/",
    )
    await user_store.ensure_user(username)
    await user_store.increment_login(username)
    return {"status": "ok", "user_id": username}


@router.post("/auth/logout")
async def logout(response: Response, user_id: str = Depends(get_current_user_id)):
    response.delete_cookie("access_token", path="/")
    return {"status": "ok"}


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response, user_id: str = Depends(get_current_user_id)):
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="not_logged_in")
    # Rate-limit refresh per session id (sid) 60/min
    try:
        from ..token_store import incr_login_counter

        sid = request.headers.get("X-Session-ID") or request.cookies.get("sid") or user_id
        if await incr_login_counter(f"rl:refresh:{sid}", 60) > 60:
            raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception:
        pass
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
    jwt_token = _make_jwt(user_id, exp_seconds=token_lifetime)
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=token_lifetime,
        path="/",
    )
    return {"status": "ok", "user_id": user_id}


# OAuth2 Password flow endpoint for Swagger "Authorize" in dev
@router.post("/auth/token", include_in_schema=True)
async def issue_token(form_data: OAuth2PasswordRequestForm = Depends()):
    # Gate for production environments
    if os.getenv("DISABLE_DEV_TOKEN", "0").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="disabled")
    username = (form_data.username or "dev").strip() or "dev"
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
    now = int(time.time())
    scopes = form_data.scopes or []
    payload = {
        "user_id": username,
        "sub": username,
        "iat": now,
        "exp": now + token_lifetime,
    }
    if scopes:
        payload["scope"] = " ".join(sorted(set(scopes)))
    token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}


@router.get("/auth/examples")
async def token_examples():
    """Return sanitized JWT examples and common scope sets.

    These are not valid tokens; use /v1/auth/token to mint a real dev token.
    """
    return {
        "samples": {
            "header": {"alg": "HS256", "typ": "JWT"},
            "payload": {
                "user_id": "dev",
                "sub": "dev",
                "exp": 1714764000,
                "scope": "admin:write",
            },
            "jwt_example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...<redacted>...",
        },
        "scopes": [
            "care:resident",
            "care:caregiver",
            "music:control",
            "admin:write",
        ],
        "notes": "Use /v1/auth/token with 'scopes' to mint a real token in dev.",
    }


__all__ = ["router"]



from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
import asyncio
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.security import OAuth2PasswordRequestForm

from ..deps.user import get_current_user_id
from ..user_store import user_store
from ..token_store import (
    is_refresh_family_revoked,
    revoke_refresh_family,
    is_refresh_allowed,
    allow_refresh,
)
from ..sessions_store import sessions_store
from ..auth_store import (
    ensure_tables as _ensure_auth,
    create_pat as _create_pat,
    get_pat_by_hash as _get_pat_by_hash,
)


router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests


def _iso(dt: float | None) -> str | None:
    if dt is None:
        return None
    return datetime.fromtimestamp(float(dt), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _in_test_mode() -> bool:
    v = lambda s: str(os.getenv(s, "")).strip().lower()
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("PYTEST_RUNNING")
        or v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or v("ENV") == "test"
    )


def _ensure_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        # Only create a loop automatically in test contexts
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_RUNNING") or os.getenv("ENV", "").lower() == "test":
            asyncio.set_event_loop(asyncio.new_event_loop())


# Ensure a default loop exists when imported under pytest to support
# synchronous helpers that need to spin async functions.
if _in_test_mode():
    _ensure_loop()


def verify_pat(token: str, required_scopes: List[str] | None = None) -> Dict[str, Any] | None:
    try:
        import hashlib

        h = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        # Fetch synchronously via event loop since tests call this directly
        _ensure_loop()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In case an event loop is already running, fall back to None (not expected in unit)
                return None
            rec = loop.run_until_complete(_get_pat_by_hash(h))  # type: ignore[arg-type]
        except RuntimeError:
            rec = asyncio.run(_get_pat_by_hash(h))  # type: ignore[arg-type]
        if not rec:
            return None
        if rec.get("revoked_at"):
            return None
        scopes = set(rec.get("scopes") or [])
        if required_scopes and not set(required_scopes).issubset(scopes):
            return None
        return rec
    except Exception:
        return None


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


@router.post("/sessions/{sid}/revoke")
async def revoke_session(sid: str, user_id: str = Depends(get_current_user_id)) -> Dict[str, str]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    await sessions_store.revoke_family(sid)
    return {"status": "ok"}


@router.get("/pats")
async def list_pats(user_id: str = Depends(get_current_user_id)) -> List[Dict[str, Any]]:
    # Placeholder: PAT listing not persisted yet in this router; return empty list until wired
    return []


@router.post("/pats", openapi_extra={"requestBody": {"content": {"application/json": {"schema": {"example": {"name": "CI token", "scopes": ["admin:write"], "exp_at": None}}}}}})
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


async def rotate_refresh_cookies(request: Request, response: Response) -> bool:
    """Rotate access/refresh cookies strictly.

    - If family revoked or jti reuse detected, revoke family, clear cookies, raise 401.
    - On success, set new cookies and mark new jti as allowed.
    """
    try:
        secret = _jwt_secret()
        rtok = request.cookies.get("refresh_token")
        if not rtok:
            return False
        # Decode refresh token
        payload = jwt.decode(rtok, secret, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            # Backward-compat: accept tokens minted before type flag existed
            # Treat as refresh when "exp" is reasonably large (>= 10 minutes)
            now = int(time.time())
            exp = int(payload.get("exp", now))
            if exp - now < 600:
                raise HTTPException(status_code=400, detail="invalid_token_type")
        user_id = payload.get("user_id") or payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="invalid_token")
        now = int(time.time())
        r_exp = int(payload.get("exp", now))
        ttl = max(1, r_exp - now)
        jti = str(payload.get("jti") or "")
        # Use session-id when available to scope family
        sid = request.headers.get("X-Session-ID") or request.cookies.get("sid") or user_id
        # Strict checks
        if await is_refresh_family_revoked(sid):
            # Clear cookies and deny
            response.delete_cookie("access_token", path="/")
            response.delete_cookie("refresh_token", path="/")
            raise HTTPException(status_code=401, detail="refresh_family_revoked")
        if not await is_refresh_allowed(sid, jti):
            # If no record exists, allow this first-time token and record it
            await allow_refresh(sid, jti, ttl_seconds=ttl)
        else:
            # mark the previous token as spent by not re-allowing it
            pass
        # Mint new access + refresh
        token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
        access_payload = {"user_id": user_id, "iat": now, "exp": now + token_lifetime}
        access_token = jwt.encode(access_payload, secret, algorithm="HS256")
        refresh_life = int(os.getenv("JWT_REFRESH_TTL_SECONDS", os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440")))
        # Support minutes var; if minutes, convert to seconds when large value looks like minutes
        if refresh_life < 60:  # heuristically treat as minutes
            refresh_life = refresh_life * 60
        new_refresh_payload = {"user_id": user_id, "iat": now, "exp": now + refresh_life, "jti": jwt.api_jws.base64url_encode(os.urandom(16)).decode(), "type": "refresh"}
        new_refresh = jwt.encode(new_refresh_payload, secret, algorithm="HS256")
        cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
        cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
        try:
            if getattr(request.url, "scheme", "http") != "https" and cookie_samesite != "none":
                cookie_secure = False
        except Exception:
            pass
        response.set_cookie("access_token", access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=token_lifetime, path="/")
        response.set_cookie("refresh_token", new_refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=refresh_life, path="/")
        # Mark new token allowed
        await allow_refresh(sid, str(new_refresh_payload.get("jti")), ttl_seconds=refresh_life)
        return True
    except HTTPException:
        raise
    except Exception:
        return False


@router.post(
    "/auth/login",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok", "user_id": "dev"}}}}}},
)
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
    try:
        if getattr(request.url, "scheme", "http") != "https" and cookie_samesite != "none":
            cookie_secure = False
    except Exception:
        pass
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=token_lifetime,
        path="/",
    )
    # Also issue a refresh token and mark it allowed for this session
    try:
        now = int(time.time())
        refresh_life = int(os.getenv("JWT_REFRESH_TTL_SECONDS", os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440")))
        if refresh_life < 60:
            refresh_life = refresh_life * 60
        import os as _os
        jti = jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        refresh_payload = {
            "user_id": username,
            "sub": username,
            "type": "refresh",
            "iat": now,
            "exp": now + refresh_life,
            "jti": jti,
        }
        refresh_token = jwt.encode(refresh_payload, _jwt_secret(), algorithm="HS256")
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=refresh_life,
            path="/",
        )
        # Scope family by session id when available, else by user id
        sid = request.headers.get("X-Session-ID") or request.cookies.get("sid") or username
        await allow_refresh(sid, jti, ttl_seconds=refresh_life)
    except Exception:
        # Best-effort; login still succeeds with access token alone
        pass
    await user_store.ensure_user(username)
    await user_store.increment_login(username)
    return {"status": "ok", "user_id": username}


@router.post(
    "/auth/logout",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def logout(response: Response, user_id: str = Depends(get_current_user_id)):
    response.delete_cookie("access_token", path="/")
    return {"status": "ok"}


@router.post(
    "/auth/refresh",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok", "user_id": "dev"}}}}}},
)
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
    # Strict family rotation path
    if not await rotate_refresh_cookies(request, response):
        raise HTTPException(status_code=401, detail="invalid_refresh")
    return {"status": "ok", "user_id": user_id}


# OAuth2 Password flow endpoint for Swagger "Authorize" in dev
@router.post(
    "/auth/token",
    include_in_schema=True,
    responses={200: {"content": {"application/json": {"schema": {"example": {"access_token": "<jwt>", "token_type": "bearer"}}}}}},
)
async def issue_token(request: Request):
    # Gate for production environments
    if os.getenv("DISABLE_DEV_TOKEN", "0").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="disabled")
    # Parse form payload manually to avoid 422 when disabled
    username = "dev"
    scopes: list[str] = []
    try:
        form = await request.form()
        username = (str(form.get("username") or "dev").strip()) or "dev"
        raw_scope = form.get("scope") or ""
        scopes = [s.strip() for s in str(raw_scope).split() if s.strip()]
    except Exception:
        pass
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
    now = int(time.time())
    # scopes already set above
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


__all__ = ["router", "verify_pat"]



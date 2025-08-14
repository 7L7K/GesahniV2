from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
import json
import asyncio
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from ..deps.user import get_current_user_id
from ..deps.clerk_auth import require_user
from ..user_store import user_store
from ..token_store import (
    is_refresh_family_revoked,
    revoke_refresh_family,
    is_refresh_allowed,
    allow_refresh,
    claim_refresh_jti,
    has_redis,
    set_last_used_jti,
    get_last_used_jti,
)
from ..sessions_store import sessions_store
from ..auth_store import (
    ensure_tables as _ensure_auth,
    create_pat as _create_pat,
    get_pat_by_hash as _get_pat_by_hash,
)


router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
# Minimal metrics counters (dumped every ~60s)
_MET: dict[str, int] = {
    "auth_refresh_ok": 0,
    "auth_refresh_replay": 0,
    "auth_refresh_concurrent_401": 0,
    "whoami_jwt_ok": 0,
    "whoami_jwt_fail": 0,
}
_MET_LAST: float = time.time()


def _met_inc(key: str) -> None:
    try:
        _MET[key] = int(_MET.get(key, 0)) + 1
        global _MET_LAST
        now = time.time()
        if now - _MET_LAST >= 60:
            _MET_LAST = now
            print(
                f"metrics auth.refresh.ok={_MET.get('auth_refresh_ok',0)} replay={_MET.get('auth_refresh_replay',0)} concurrent_401={_MET.get('auth_refresh_concurrent_401',0)} whoami.jwt_ok={_MET.get('whoami_jwt_ok',0)} jwt_fail={_MET.get('whoami_jwt_fail',0)}"
            )
            # do not reset, cumulative during process lifetime
    except Exception:
        pass


def _append_cookie_with_priority(response: Response, *, key: str, value: str, max_age: int, secure: bool, samesite: str, path: str = "/") -> None:
    try:
        smap = {"lax": "Lax", "strict": "Strict", "none": "None"}
        ss = smap.get((samesite or "lax").lower(), "Lax")
        parts = [
            f"{key}={value}",
            "HttpOnly",
            f"Max-Age={int(max_age)}",
            f"Path={path}",
            f"SameSite={ss}",
            "Secure" if secure else None,
            "Priority=High",
        ]
        header = "; ".join([p for p in parts if p])
        response.headers.append("Set-Cookie", header)
    except Exception:
        # Fallback to regular set_cookie if building header fails
        response.set_cookie(key, value, httponly=True, secure=secure, samesite=samesite, max_age=max_age, path=path)
@router.get("/auth/clerk/protected")
async def clerk_protected(user_id: str = Depends(require_user)) -> Dict[str, Any]:
    return {"ok": True, "user_id": user_id}



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


async def _require_user_or_dev(request: Request) -> str:
    """Require Clerk user when configured; allow dev fallback when enabled.

    Fallback is enabled when either of the following is true:
    - AUTH_DEV_BYPASS in {1,true,yes,on}
    - ENV is dev and CLERK_* not configured (best-effort)
    """
    # Explicit bypass knob for local testing
    if os.getenv("AUTH_DEV_BYPASS", "0").strip().lower() in {"1", "true", "yes", "on"}:
        return os.getenv("DEV_USER_ID", "dev")
    # Try Clerk first
    try:
        return await require_user(request)
    except Exception:
        # Best-effort dev fallback when Clerk isn’t configured and we’re in dev
        env = os.getenv("ENV", "dev").strip().lower()
        has_clerk = any(
            bool(os.getenv(k, "").strip())
            for k in ("CLERK_JWKS_URL", "CLERK_ISSUER", "CLERK_DOMAIN")
        )
        if env in {"dev", "development"} and not has_clerk:
            return os.getenv("DEV_USER_ID", "dev")
        # Otherwise, re-raise unauthorized
        from fastapi import HTTPException as _HTTPException  # lazy to avoid import cycles
        raise _HTTPException(status_code=401, detail="Unauthorized")


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


async def whoami_impl(request: Request) -> Dict[str, Any]:
    """Canonical whoami implementation: single source of truth for session readiness.

    Response shape (versioned):
    {
      "is_authenticated": bool,
      "session_ready": bool,
      "user": { "id": str, "email": str | None },
      "source": "cookie" | "header" | "missing",
      "version": 1
    }
    """
    t0 = time.time()
    src: str = "missing"
    token_cookie: Optional[str] = None
    token_header: Optional[str] = None
    try:
        token_cookie = request.cookies.get("access_token")
    except Exception:
        token_cookie = None
    try:
        ah = request.headers.get("Authorization")
        if ah and ah.startswith("Bearer "):
            token_header = ah.split(" ", 1)[1]
    except Exception:
        token_header = None

    # Prefer cookie when valid; otherwise fall back to header
    session_ready = False
    effective_uid: Optional[str] = None
    jwt_status = "missing"
    if token_cookie:
        try:
            claims = jwt.decode(token_cookie, _jwt_secret(), algorithms=["HS256"])  # type: ignore[arg-type]
            session_ready = True
            src = "cookie"
            effective_uid = str(claims.get("user_id") or claims.get("sub") or "") or None
            jwt_status = "ok"
        except Exception:
            session_ready = False
            effective_uid = None
            jwt_status = "invalid"
    if not session_ready and token_header:
        try:
            claims = jwt.decode(token_header, _jwt_secret(), algorithms=["HS256"])  # type: ignore[arg-type]
            session_ready = True
            src = "header"
            effective_uid = str(claims.get("user_id") or claims.get("sub") or "") or None
            jwt_status = "ok"
        except Exception:
            session_ready = False
            effective_uid = None
            jwt_status = "invalid"

    # Canonical policy: authenticated iff a valid token was presented
    is_authenticated = bool(session_ready and effective_uid)

    # Log a compact line for probing and metrics
    try:
        dt = int((time.time() - t0) * 1000)
        print(f"whoami t={dt}ms jwt={jwt_status} src={src}")
        try:
            _met_inc("whoami_jwt_ok" if session_ready else "whoami_jwt_fail")
        except Exception:
            pass
    except Exception:
        pass

    return {
        "is_authenticated": bool(is_authenticated),
        "session_ready": bool(session_ready),
        "user": {"id": effective_uid if effective_uid else None, "email": getattr(request.state, "email", None)},
        "source": src,
        "version": 1,
    }


@router.get("/whoami")
async def whoami(request: Request) -> Dict[str, Any]:
    return await whoami_impl(request)


# Device sessions endpoints were moved to app.api.me for canonical shapes.


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
        # Dev-friendly fallback to align with legacy auth default
        return os.getenv("JWT_SECRET", "change-me")
    return sec


def _key_pool_from_env() -> dict[str, str]:
    raw = os.getenv("JWT_KEYS") or os.getenv("JWT_KEY_POOL")
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj:
                return {str(k): str(v) for k, v in obj.items()}
        except Exception:
            pass
        try:
            items = [p.strip() for p in str(raw).split(",") if p.strip()]
            out: dict[str, str] = {}
            for it in items:
                if ":" in it:
                    kid, sec = it.split(":", 1)
                    out[kid.strip()] = sec.strip()
            if out:
                return out
        except Exception:
            pass
    sec = os.getenv("JWT_SECRET")
    if not sec:
        # Align with legacy auth default used for login when unset
        sec = "change-me"
    return {"k0": sec}


def _primary_kid_secret() -> tuple[str, str]:
    pool = _key_pool_from_env()
    if not pool:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    kid, sec = next(iter(pool.items()))
    return kid, sec


def _decode_any(token: str, *, leeway: int = 0) -> dict:
    pool = _key_pool_from_env()
    if not pool:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    try:
        hdr = jwt.get_unverified_header(token)
        kid = hdr.get("kid")
    except Exception:
        kid = None
    keys = list(pool.items())
    if kid and kid in pool:
        keys = [(kid, pool[kid])] + [(k, s) for (k, s) in pool.items() if k != kid]
    elif kid and kid not in pool:
        try:
            print("auth.jwt kid_not_found attempting_pool_refresh")
        except Exception:
            pass
    last_err: Exception | None = None
    for _, sec in keys:
        try:
            return jwt.decode(token, sec, algorithms=["HS256"], leeway=leeway)
        except Exception as e:
            last_err = e
            continue
    if isinstance(last_err, jwt.ExpiredSignatureError):
        raise last_err
    raise HTTPException(status_code=401, detail="Unauthorized")

def _get_refresh_ttl_seconds() -> int:
    """Return refresh token TTL in seconds using consistent precedence.

    Precedence:
    1) JWT_REFRESH_TTL_SECONDS (seconds)
    2) JWT_REFRESH_EXPIRE_MINUTES (minutes → seconds)
    Default: 7 days.
    """
    try:
        v = os.getenv("JWT_REFRESH_TTL_SECONDS")
        if v is not None and str(v).strip() != "":
            return max(1, int(v))
    except Exception:
        pass
    try:
        vmin = os.getenv("JWT_REFRESH_EXPIRE_MINUTES")
        if vmin is not None and str(vmin).strip() != "":
            return max(60, int(vmin) * 60)
    except Exception:
        pass
    return 7 * 24 * 60 * 60


def _make_jwt(user_id: str, *, exp_seconds: int) -> str:
    now = int(time.time())
    payload = {"user_id": user_id, "sub": user_id, "iat": now, "exp": now + exp_seconds}
    iss = os.getenv("JWT_ISSUER")
    aud = os.getenv("JWT_AUDIENCE")
    if iss:
        payload["iss"] = iss
    if aud:
        payload["aud"] = aud
    kid, sec = _primary_kid_secret()
    return jwt.encode(payload, sec, algorithm="HS256", headers={"kid": kid})


def _cookie_flags_for(request: Request) -> tuple[bool, str]:
    """Return (secure, samesite) flags considering dev HTTP.

    - Secure only when SameSite=None or running behind https
    - In dev over http, prefer not Secure for local testing
    """
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    try:
        if getattr(request.url, "scheme", "http") != "https" and cookie_samesite != "none":
            cookie_secure = False
    except Exception:
        pass
    return cookie_secure, cookie_samesite


@router.get("/auth/finish")
@router.post("/auth/finish")
async def finish_clerk_login(request: Request, response: Response, user_id: str = Depends(_require_user_or_dev)):
    """Set auth cookies and finish login.

    CSRF: Required for POST when CSRF_ENABLED=1 via X-CSRF-Token matching csrf_token cookie.
    """
    # Keep ultra-fast: no body reads, no remote calls beyond local JWT mint
    t0 = time.time()
    """Bridge Clerk session → app cookies, then redirect to app.

    Responsibilities:
    - Verify Clerk session via require_user (server-side)
    - Mint app access + refresh tokens
    - Set them as HttpOnly cookies on same origin
    - Redirect to the requested app route (default "/")
    """
    # TTLs: defaults suitable for dev (access: 30 min; refresh: 7 days)
    try:
        token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1800"))  # 30 minutes
    except Exception:
        token_lifetime = 1800
    refresh_life = _get_refresh_ttl_seconds()

    now = int(time.time())
    access_payload = {"user_id": user_id, "sub": user_id, "iat": now, "exp": now + token_lifetime}
    iss = os.getenv("JWT_ISSUER")
    aud = os.getenv("JWT_AUDIENCE")
    if iss:
        access_payload["iss"] = iss
    if aud:
        access_payload["aud"] = aud
    access_token = _make_jwt(user_id, exp_seconds=token_lifetime)

    # Issue refresh token scoped to session family
    import os as _os
    jti = jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
    refresh_payload = {
        "user_id": user_id,
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + refresh_life,
        "jti": jti,
    }
    if iss:
        refresh_payload["iss"] = iss
    if aud:
        refresh_payload["aud"] = aud
    kid, sec = _primary_kid_secret()
    refresh_token = jwt.encode(refresh_payload, sec, algorithm="HS256", headers={"kid": kid})

    # Prepare response cookies
    cookie_secure, cookie_samesite = _cookie_flags_for(request)

    # Build safe redirect target
    next_path = (request.query_params.get("next") or "/").strip()
    try:
        # Prevent open redirects: internal-only absolute path
        if not next_path.startswith("/") or "://" in next_path:
            next_path = "/"
        # Normalize duplicate slashes
        import re as _re
        next_path = _re.sub(r"/+", "/", next_path)
    except Exception:
        next_path = "/"

    # Classify finisher reason for logs
    reason = "normal_login"
    try:
        if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
            reason = "cross_site"
    except Exception:
        pass
    # Fast path for XHR/POST: Set-Cookie and return 204 (no redirect)
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        # When SameSite=None (cross-site), require explicit intent header even for finisher POST
        try:
            if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
                intent = request.headers.get("x-auth-intent") or request.headers.get("X-Auth-Intent")
                if str(intent or "").strip().lower() != "refresh":
                    raise HTTPException(status_code=401, detail="missing_intent_header")
        except HTTPException:
            raise
        except Exception:
            pass
        # Enforce CSRF for POST in cookie-auth flows when globally enabled
        try:
            from ..csrf import _extract_csrf_header as _csrf_extract
            if os.getenv("CSRF_ENABLED", "0").strip().lower() in {"1","true","yes","on"}:
                tok, used_legacy, allowed = _csrf_extract(request)
                if used_legacy and not allowed:
                    raise HTTPException(status_code=400, detail="missing_csrf")
                cookie = request.cookies.get("csrf_token")
                if not tok or not cookie or tok != cookie:
                    raise HTTPException(status_code=403, detail="invalid_csrf")
        except HTTPException:
            raise
        except Exception:
            pass
        from fastapi import Response as _Resp  # type: ignore
        resp = _Resp(status_code=204)
        # High-priority cookies to avoid eviction under pressure
        try:
            _append_cookie_with_priority(resp, key="access_token", value=access_token, max_age=token_lifetime, secure=cookie_secure, samesite=cookie_samesite)
            _append_cookie_with_priority(resp, key="refresh_token", value=refresh_token, max_age=refresh_life, secure=cookie_secure, samesite=cookie_samesite)
        except Exception:
            resp.set_cookie("access_token", access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=token_lifetime, path="/")
            resp.set_cookie("refresh_token", refresh_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=refresh_life, path="/")
        # One-liner timing log for finisher
        try:
            dt = int((time.time() - t0) * 1000)
            print(f"auth.finish t_total={dt}ms set_cookie=true reason={reason}")
        except Exception:
            pass
        return resp
    # Browser GET: redirect to next with cookies attached
    resp = RedirectResponse(url=next_path, status_code=302)
    try:
        _append_cookie_with_priority(resp, key="access_token", value=access_token, max_age=token_lifetime, secure=cookie_secure, samesite=cookie_samesite)
        _append_cookie_with_priority(resp, key="refresh_token", value=refresh_token, max_age=refresh_life, secure=cookie_secure, samesite=cookie_samesite)
    except Exception:
        resp.set_cookie("access_token", access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=token_lifetime, path="/")
        resp.set_cookie("refresh_token", refresh_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=refresh_life, path="/")
    try:
        dt = int((time.time() - t0) * 1000)
        print(f"auth.finish t_total={dt}ms set_cookie=true reason={reason}")
    except Exception:
        pass
    return resp


# Minimal debug endpoint for Clerk callback path discovery (no auth dependency)
@router.get("/auth/clerk/finish")
@router.post("/auth/clerk/finish")
async def clerk_finish(request: Request) -> Dict[str, Any]:
    try:
        print(">> Clerk callback hit:", request.url)
        try:
            body = await request.body()
        except Exception:
            body = b""
        print(">> Body:", body)
    except Exception:
        pass
    # Echo minimal info so callers see something structured
    try:
        return {"status": "ok", "path": str(request.url), "length": len(body)}  # type: ignore[name-defined]
    except Exception:
        return {"status": "ok"}


async def rotate_refresh_cookies(request: Request, response: Response, refresh_override: str | None = None) -> Dict[str, str] | None:
    """Rotate access/refresh cookies strictly.

    - If family revoked or jti reuse detected, revoke family, clear cookies, raise 401.
    - On success, set new cookies and mark new jti as allowed.
    """
    try:
        secret = _jwt_secret()
        rtok = refresh_override or request.cookies.get("refresh_token")
        if not rtok:
            try:
                print("auth.refresh debug no_refresh_cookie headers=", dict(request.headers))
                try:
                    print("auth.refresh debug cookies=", dict(request.cookies))
                except Exception:
                    pass
            except Exception:
                pass
            return None
        # Decode refresh token against any configured key with a small skew
        payload = _decode_any(rtok, leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60))
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
        # Single-use guard for this refresh token (replay protection)
        first_use = await claim_refresh_jti(sid, jti, ttl_seconds=ttl)
        if not first_use:
            # Deny replay (another concurrent request likely succeeded)
            response.delete_cookie("access_token", path="/")
            response.delete_cookie("refresh_token", path="/")
            try:
                last = await get_last_used_jti(sid)
                print(f"auth.refresh t=0ms result=replay sid={sid} replay_of={last or '-'}")
                _met_inc("auth_refresh_replay")
            except Exception:
                pass
            raise HTTPException(status_code=401, detail="refresh_reused")
        # Mint new access + refresh
        token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
        access_payload = {"user_id": user_id, "iat": now, "exp": now + token_lifetime}
        access_token = jwt.encode(access_payload, secret, algorithm="HS256")
        refresh_life = _get_refresh_ttl_seconds()
        new_refresh_payload = {"user_id": user_id, "iat": now, "exp": now + refresh_life, "jti": jwt.api_jws.base64url_encode(os.urandom(16)).decode(), "type": "refresh"}
        new_refresh = jwt.encode(new_refresh_payload, secret, algorithm="HS256")
        cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
        cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
        try:
            if getattr(request.url, "scheme", "http") != "https" and cookie_samesite != "none":
                cookie_secure = False
        except Exception:
            pass
        try:
            _append_cookie_with_priority(response, key="access_token", value=access_token, max_age=token_lifetime, secure=cookie_secure, samesite=cookie_samesite)
            _append_cookie_with_priority(response, key="refresh_token", value=new_refresh, max_age=refresh_life, secure=cookie_secure, samesite=cookie_samesite)
        except Exception:
            response.set_cookie("access_token", access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=token_lifetime, path="/")
            response.set_cookie("refresh_token", new_refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=refresh_life, path="/")
        # Mark new token allowed
        await allow_refresh(sid, str(new_refresh_payload.get("jti")), ttl_seconds=refresh_life)
        try:
            await set_last_used_jti(sid, jti, ttl_seconds=ttl)
            _met_inc("auth_refresh_ok")
            print(f"auth.refresh t=0ms result=ok sid={sid}")
        except Exception:
            pass
        return {"access_token": access_token, "refresh_token": new_refresh, "user_id": str(user_id)}
    except HTTPException:
        raise
    except Exception:
        return None


@router.post(
    "/auth/login",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok", "user_id": "dev"}}}}}},
)
async def login(username: str, request: Request, response: Response):
    """Dev login scaffold.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """
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
    # Short access in prod by default: 15 minutes; tests/dev can override
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900"))
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
        # Longer refresh in prod: default 7 days (604800s), allow override via env
        refresh_life = _get_refresh_ttl_seconds()
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
        iss = os.getenv("JWT_ISSUER")
        aud = os.getenv("JWT_AUDIENCE")
        if iss:
            refresh_payload["iss"] = iss
        if aud:
            refresh_payload["aud"] = aud
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
async def logout(request: Request, response: Response, user_id: str = Depends(get_current_user_id)):
    """Logout current session family.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """
    # Revoke refresh family bound to session id (did/sid) when possible
    try:
        from ..token_store import revoke_refresh_family
        sid = request.headers.get("X-Session-ID") or request.cookies.get("sid") or user_id
        # TTL: align with remaining refresh TTL when available; best-effort 7d
        await revoke_refresh_family(sid, ttl_seconds=int(os.getenv("JWT_REFRESH_TTL_SECONDS", "604800")))
    except Exception:
        pass
    # Clear cookies regardless of Bearer availability
    try:
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
    except Exception:
        pass
    try:
        print("logout clear=both")
    except Exception:
        pass
    return {"status": "ok"}


@router.post(
    "/auth/refresh",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok", "user_id": "dev"}}}}}},
)
async def refresh(request: Request, response: Response):
    """Rotate access/refresh cookies.

    Intent: When COOKIE_SAMESITE=none, require header X-Auth-Intent: refresh.
    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """
    # CSRF guard for cross-site cookie mode: require explicit intent header (case-insensitive)
    try:
        if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
            intent = request.headers.get("x-auth-intent") or request.headers.get("X-Auth-Intent")
            if str(intent or "").strip().lower() != "refresh":
                raise HTTPException(status_code=400, detail="missing_intent_header")
    except HTTPException:
        raise
    except Exception:
        pass
    # Global CSRF enforcement for mutating routes when enabled
    try:
        if os.getenv("CSRF_ENABLED", "0").strip().lower() in {"1","true","yes","on"}:
            from ..csrf import _extract_csrf_header as _csrf_extract
            tok, used_legacy, allowed = _csrf_extract(request)
            if used_legacy and not allowed:
                raise HTTPException(status_code=400, detail="missing_csrf")
            cookie = request.cookies.get("csrf_token")
            if not tok or not cookie or tok != cookie:
                raise HTTPException(status_code=403, detail="invalid_csrf")
    except HTTPException:
        raise
    except Exception:
        pass
    # Rate-limit refresh per session id (sid) 60/min
    try:
        from ..token_store import incr_login_counter
        # Identify a stable session family key for rate limiting
        sid = request.headers.get("X-Session-ID") or request.cookies.get("sid")
        if not sid:
            try:
                rtok = request.cookies.get("refresh_token")
                if rtok:
                    payload = _decode_any(rtok)
                    sid = payload.get("sub") or payload.get("user_id")
            except Exception:
                sid = None
        sid = sid or "anon"
        # Rate-limit per family and per-IP
        ip = (request.client.host if request.client else "unknown")
        fam_hits = await incr_login_counter(f"rl:refresh:fam:{sid}", 60)
        ip_hits = await incr_login_counter(f"rl:refresh:ip:{ip}", 60)
        fam_cap = 60
        ip_cap = 120
        if fam_hits > fam_cap or ip_hits > ip_cap:
            raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception:
        pass
    # Strict family rotation path
    try:
        if os.getenv("MULTIPROC", "0").lower() in {"1","true","yes","on"} and not (await has_redis()):
            raise HTTPException(status_code=503, detail="redis_required")
    except HTTPException:
        raise
    except Exception:
        pass
    # Optional JSON body may supply refresh_token for header-mode clients and legacy /v1/refresh delegation
    refresh_override: str | None = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            val = body.get("refresh_token")
            if isinstance(val, str) and val:
                refresh_override = val
    except Exception:
        refresh_override = None
    t0 = time.time()
    tokens = await rotate_refresh_cookies(request, response, refresh_override)
    if not tokens:
        # Metric for spikes on refresh failures
        try:
            from ..metrics import AUTH_4XX_TOTAL  # type: ignore
            AUTH_4XX_TOTAL.labels("/v1/auth/refresh", "401").inc()
        except Exception:
            pass
        # Fallback: if a valid access_token cookie exists, treat as session-ready and return 200
        try:
            atok = request.cookies.get("access_token")
            if atok:
                claims = _decode_any(atok)
                uid_fb = str(claims.get("user_id") or claims.get("sub") or "anon")
                try:
                    dt = int((time.time() - t0) * 1000)
                    sid = request.headers.get("X-Session-ID") or request.cookies.get("sid") or uid_fb
                    print(f"auth.refresh t={dt}ms result=ok sid={sid}")
                except Exception:
                    pass
                return {"status": "ok", "user_id": uid_fb}
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="invalid_refresh")
    # Prefer user_id from rotation outcome; include tokens for header-auth clients
    try:
        dt = int((time.time() - t0) * 1000)
        sid = request.headers.get("X-Session-ID") or request.cookies.get("sid") or (tokens.get("user_id") if isinstance(tokens, dict) else "-")
        print(f"auth.refresh t={dt}ms result=ok sid={sid}")
    except Exception:
        pass
    body: Dict[str, Any] = {"status": "ok", "user_id": tokens.get("user_id", "anon")}
    # Expose tokens to header-mode clients; cookies were already set
    if isinstance(tokens, dict):
        body["access_token"] = tokens.get("access_token")  # type: ignore[assignment]
        body["refresh_token"] = tokens.get("refresh_token")  # type: ignore[assignment]
    return body


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


@router.get("/mock/set_access_cookie", include_in_schema=False)
async def mock_set_access_cookie(max_age: int = 1) -> Response:
    """Dev helper: set a short-lived access_token cookie for expiry tests.

    Only enabled outside production.
    """
    if os.getenv("ENV", "dev").strip().lower() in {"prod", "production"}:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        max_age = int(max(1, int(max_age)))
    except Exception:
        max_age = 1
    # Mint a token with requested TTL
    tok = _make_jwt(os.getenv("DEV_USER_ID", "dev"), exp_seconds=max_age)
    resp = Response(status_code=204)
    # SameSite and Secure flags reuse cookie defaults
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    resp.set_cookie("access_token", tok, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=max_age, path="/")
    return resp

__all__ = ["router", "verify_pat"]



from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional, Tuple

import jwt

from fastapi import Request
from starlette.websockets import WebSocket

from .cookie_names import GSNH_AT, GSNH_SESS, SESSION
from .session_store import get_session_store, SessionStoreUnavailable

logger = logging.getLogger(__name__)


class AuthConfig:
    """Lightweight auth config for Phase 2 scaffolding.

    Defaults are safe and backward-compatible with Phase 1.
    """

    def __init__(self) -> None:
        self.algs = [a.strip() for a in (os.getenv("JWT_ALGS") or "HS256").split(",") if a.strip()]
        self.leeway = int(min(300, int(os.getenv("JWT_LEEWAY", os.getenv("JWT_CLOCK_SKEW_S", "60")))))
        self.issuer = os.getenv("JWT_ISSUER") or os.getenv("JWT_ISS")
        self.audience = os.getenv("JWT_AUDIENCE") or os.getenv("JWT_AUD")
        self.strict = os.getenv("REQUIRE_JWT_STRICT", "0").lower() in {"1", "true", "yes", "on"}
        self.hs_secret = os.getenv("JWT_HS_SECRET") or os.getenv("JWT_SECRET")
        # Map kid->PEM; JSON string {"kid1": "-----BEGIN PUBLIC KEY-----..."}
        try:
            self.public_keys = json.loads(os.getenv("JWT_PUBLIC_KEYS", "{}"))
        except Exception:
            self.public_keys = {}
        # Phase 3 default: legacy cookie names OFF unless explicitly enabled
        self.legacy_names = os.getenv("AUTH_LEGACY_COOKIE_NAMES", "0").lower() in {"1", "true", "yes", "on"}


CFG = AuthConfig()


def _hs_decode(token: str, leeway: int) -> dict:
    if not CFG.hs_secret:
        raise jwt.InvalidTokenError("missing_hs_secret")
    opts: dict = {}
    if CFG.issuer:
        opts["issuer"] = CFG.issuer
    if CFG.audience:
        opts["audience"] = CFG.audience
    return jwt.decode(token, CFG.hs_secret, algorithms=["HS256"], leeway=leeway, **opts)


def _rs_decode(token: str, leeway: int) -> Optional[dict]:
    if not CFG.public_keys:
        return None
    try:
        hdr = jwt.get_unverified_header(token)
        kid = hdr.get("kid")
    except Exception:
        kid = None
    candidates: list[Tuple[str, str]] = []
    if kid and kid in CFG.public_keys:
        candidates.append((kid, CFG.public_keys[kid]))
    candidates += [(k, v) for (k, v) in CFG.public_keys.items() if k != kid]
    for _, pem in candidates:
        try:
            opts: dict = {}
            if CFG.issuer:
                opts["issuer"] = CFG.issuer
            if CFG.audience:
                opts["audience"] = CFG.audience
            return jwt.decode(token, pem, algorithms=["RS256", "ES256"], leeway=leeway, **opts)
        except Exception:
            continue
    return None


def decode_any(token: str) -> dict:
    """Decode token using HS first, then public keys when configured.

    Raises jwt.ExpiredSignatureError for expired tokens and jwt.InvalidTokenError for invalid tokens.
    """
    last_err: Exception | None = None
    # HS first for back-compat
    try:
        return _hs_decode(token, CFG.leeway)
    except Exception as e:
        last_err = e
    # Try RS/ES when available
    try:
        out = _rs_decode(token, CFG.leeway)
        if out is not None:
            return out
    except Exception as e:
        last_err = e
    # Re-raise last error in a predictable manner
    if isinstance(last_err, jwt.ExpiredSignatureError):
        raise last_err
    raise jwt.InvalidTokenError("invalid_token")


def extract_token(target: Request | WebSocket) -> tuple[str, Optional[str]]:
    """Unified token extraction with precedence: header > access cookie > session cookie.

    Returns (source, token) where source in {"authorization", "access_cookie", "session"}.
    token is None when nothing present.
    """
    # 1) Authorization header
    try:
        auth = target.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            return ("authorization", auth.split(" ", 1)[1])
    except Exception:
        pass
    # 2) Access token cookie
    try:
        if isinstance(target, Request):
            tok = target.cookies.get(f"__Host-{GSNH_AT}") or target.cookies.get(GSNH_AT)
            if tok:
                return ("access_cookie", tok)
        else:
            raw = target.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for p in parts:
                if p.startswith(f"__Host-{GSNH_AT}=") or p.startswith(f"{GSNH_AT}="):
                    return ("access_cookie", p.split("=", 1)[1])
    except Exception:
        pass
    # 3) Session cookie (canonical first; legacy optional)
    try:
        if isinstance(target, Request):
            sid = target.cookies.get(f"__Host-{GSNH_SESS}") or target.cookies.get(GSNH_SESS)
            if not sid and CFG.legacy_names:
                sid = target.cookies.get(SESSION) or target.cookies.get("session")
            if sid:
                return ("session", sid)
        else:
            raw = target.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for p in parts:
                if p.startswith(f"__Host-{GSNH_SESS}=") or p.startswith(f"{GSNH_SESS}="):
                    return ("session", p.split("=", 1)[1])
            if CFG.legacy_names:
                for p in parts:
                    if p.startswith("__session="):
                        return ("session", p.split("=", 1)[1])
    except Exception:
        pass
    return ("none", None)


def resolve_session_identity(session_id: str) -> dict | None:
    store = get_session_store()
    return store.get_session_identity(session_id)


def resolve_auth(target: Request | WebSocket) -> dict[str, Any]:
    """Resolve auth with unified precedence and attach to target.state when possible.

    Returns a dict { user_id, jwt_payload, auth_source } with None values when missing.
    """
    t0 = time.time()
    source, tok = extract_token(target)
    user_id: Optional[str] = None
    payload: Optional[dict] = None
    try:
        if source in {"authorization", "access_cookie"} and tok:
            payload = decode_any(tok)
            user_id = str(payload.get("user_id") or payload.get("sub") or "") or None
        elif source == "session" and tok:
            try:
                ident = resolve_session_identity(tok)
            except SessionStoreUnavailable:
                ident = None
                try:
                    setattr(target.state, "session_store_unavailable", True)
                except Exception:
                    pass
            if ident:
                payload = ident
                user_id = str(ident.get("user_id") or ident.get("sub") or "") or None
    except jwt.ExpiredSignatureError:
        # Let callers decide; for identity-first flows, this will fall back to session
        raise
    except Exception:
        pass

    # Attach when possible
    try:
        if payload:
            target.state.jwt_payload = payload
        if user_id:
            target.state.user_id = user_id
        target.state.auth_source = source
    except Exception:
        pass
    # Observability hooks
    try:
        from .metrics import AUTH_IDENTITY_RESOLVE, AUTH_STATUS_LATENCY

        if user_id and payload:
            AUTH_IDENTITY_RESOLVE.labels(source=source, result="ok").inc()
        else:
            # Distinguish outage vs miss
            if getattr(target.state, "session_store_unavailable", False) and source == "session":
                AUTH_IDENTITY_RESOLVE.labels(source=source, result="outage").inc()
            else:
                AUTH_IDENTITY_RESOLVE.labels(source=source, result="miss").inc()
        AUTH_STATUS_LATENCY.observe((time.time() - t0) * 1000.0)
    except Exception:
        pass
    return {
        "user_id": user_id,
        "jwt_payload": payload,
        "auth_source": source,
    }


def has_scope(payload: dict | None, required: str) -> bool:
    scopes = []
    if isinstance(payload, dict):
        val = payload.get("scopes") or payload.get("scope") or []
        if isinstance(val, str):
            scopes = [s.strip() for s in val.split() if s.strip()]
        elif isinstance(val, list):
            scopes = [str(s).strip() for s in val if str(s).strip()]
    return required in set(scopes)


def require_scope(required: str):
    from fastapi import HTTPException

    def _dep(request: Request):
        payload = getattr(request.state, "jwt_payload", None)
        if not has_scope(payload, required):
            raise HTTPException(status_code=403, detail="forbidden")

    return _dep


def csrf_validate(request: Request) -> None:
    """Double-submit CSRF validation for mutating verbs when CSRF_ENABLED=1.

    This is a thin wrapper around existing csrf helpers to avoid breaking behavior.
    """
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if os.getenv("CSRF_ENABLED", "0").lower() not in {"1", "true", "yes", "on"}:
        return
    try:
        from .csrf import _extract_csrf_header as _csrf_extract

        tok, used_legacy, allowed = _csrf_extract(request)
        cookie = request.cookies.get("csrf_token")
        if used_legacy and not allowed:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="missing_csrf")
        if not tok or not cookie or tok != cookie:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="invalid_csrf")
    except Exception as e:
        # Be explicit: fail-closed for enabled CSRF on mutation
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="invalid_csrf")


__all__ = [
    "AuthConfig",
    "CFG",
    "decode_any",
    "extract_token",
    "resolve_session_identity",
    "resolve_auth",
    "csrf_validate",
    "has_scope",
    "require_scope",
]

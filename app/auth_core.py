from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional, Tuple

import jwt
from .security import jwt_decode

from fastapi import Request
from starlette.websockets import WebSocket

from .cookie_names import GSNH_AT, GSNH_SESS, SESSION, ACCESS_TOKEN
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
    return jwt_decode(token, CFG.hs_secret, algorithms=["HS256"], leeway=leeway, **opts)


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
            return jwt_decode(token, pem, algorithms=["RS256", "ES256"], leeway=leeway, **opts)
        except Exception:
            continue
    return None


def decode_any(token: str, leeway: int = None) -> dict:
    """Decode token using HS first, then public keys when configured.

    Raises jwt.ExpiredSignatureError for expired tokens and jwt.InvalidTokenError for invalid tokens.

    Args:
        token: JWT token to decode
        leeway: Custom leeway in seconds, uses CFG.leeway if None
    """
    if leeway is None:
        leeway = CFG.leeway

    last_err: Exception | None = None
    # HS first for back-compat
    try:
        return _hs_decode(token, leeway)
    except Exception as e:
        last_err = e
    # Try RS/ES when available
    try:
        out = _rs_decode(token, leeway)
        if out is not None:
            return out
    except Exception as e:
        last_err = e
    # Re-raise last error in a predictable manner
    if isinstance(last_err, jwt.ExpiredSignatureError):
        raise last_err
    raise jwt.InvalidTokenError("invalid_token")


def decode_with_leeway(token: str, operation: str = "default") -> dict:
    """Decode token with operation-specific leeway handling.

    Args:
        token: JWT token to decode
        operation: Operation type for leeway calculation ("refresh", "access", "default")

    Returns:
        Decoded token payload

    Raises:
        jwt.ExpiredSignatureError: Token is expired
        jwt.InvalidTokenError: Token is invalid
    """
    # Calculate operation-specific leeway
    base_leeway = CFG.leeway

    # Increase leeway for refresh operations to handle clock skew
    if operation == "refresh":
        leeway = min(base_leeway * 2, 300)  # Max 5 minutes for refresh
    elif operation == "access":
        leeway = base_leeway
    else:
        leeway = base_leeway

    try:
        return decode_any(token, leeway)
    except jwt.ExpiredSignatureError:
        # Record leeway usage for monitoring
        try:
            from .metrics_auth import record_jwt_leeway_usage
            record_jwt_leeway_usage(operation, leeway)
        except Exception:
            pass
        raise
    except jwt.InvalidTokenError as e:
        # Record validation failure
        try:
            from .metrics_auth import record_token_validation
            record_token_validation("jwt", "failed")
        except Exception:
            pass
        raise


def validate_token_expiry(payload: dict, grace_period: int = 0) -> bool:
    """Validate token expiry with optional grace period.

    Args:
        payload: Token payload
        grace_period: Additional grace period in seconds

    Returns:
        True if token is valid (not expired), False otherwise
    """
    try:
        exp = int(payload.get("exp", 0))
        if exp == 0:
            return False

        now = int(time.time())
        return (exp + grace_period) > now
    except Exception:
        return False


def get_token_expiry_info(payload: dict) -> dict:
    """Get detailed expiry information for a token.

    Returns:
        Dict with expiry information:
        - exp: expiration timestamp
        - seconds_until_expiry: seconds until expiry
        - is_expired: boolean
        - is_expiring_soon: boolean (within 5 minutes)
    """
    try:
        exp = int(payload.get("exp", 0))
        now = time.time()

        if exp == 0:
            return {
                "exp": 0,
                "seconds_until_expiry": 0,
                "is_expired": True,
                "is_expiring_soon": True,
            }

        seconds_until = exp - now
        is_expired = seconds_until <= 0
        is_expiring_soon = seconds_until <= 300  # 5 minutes

        return {
            "exp": exp,
            "seconds_until_expiry": max(0, seconds_until),
            "is_expired": is_expired,
            "is_expiring_soon": is_expiring_soon,
        }
    except Exception:
        return {
            "exp": 0,
            "seconds_until_expiry": 0,
            "is_expired": True,
            "is_expiring_soon": True,
        }


def extract_token_metadata(token: str) -> dict:
    """Extract metadata from a JWT token without full validation.

    Useful for logging and monitoring without exposing sensitive claims.

    Returns:
        Dict with token metadata (safe for logging)
    """
    try:
        # Get unverified header
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg", "unknown")
        token_type = header.get("typ", "JWT")

        # Try to get basic claims without verification
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            user_id = unverified.get("sub") or unverified.get("user_id", "unknown")
            token_type_claim = unverified.get("type", "unknown")
            jti = unverified.get("jti", "unknown")
            exp = unverified.get("exp", 0)
            iat = unverified.get("iat", 0)

            return {
                "algorithm": algorithm,
                "type": token_type,
                "token_type": token_type_claim,
                "user_id_hash": hash(user_id) if user_id != "unknown" else "unknown",
                "jti": jti,
                "exp": exp,
                "iat": iat,
                "is_expired": exp > 0 and exp < time.time(),
                "length": len(token),
            }
        except Exception:
            # If we can't decode at all, return minimal info
            return {
                "algorithm": algorithm,
                "type": token_type,
                "token_type": "unknown",
                "user_id_hash": "unknown",
                "jti": "unknown",
                "exp": 0,
                "iat": 0,
                "is_expired": True,
                "length": len(token),
            }
    except Exception:
        return {
            "algorithm": "unknown",
            "type": "unknown",
            "token_type": "unknown",
            "user_id_hash": "unknown",
            "jti": "unknown",
            "exp": 0,
            "iat": 0,
            "is_expired": True,
            "length": len(token) if token else 0,
        }


def extract_token(target: Request | WebSocket) -> tuple[str, Optional[str]]:
    """Unified token extraction with precedence: access cookie > header > session cookie.

    Returns (source, token) where source in {"access_cookie", "authorization", "session"}.
    token is None when nothing present.
    """
    # 1) Access token cookie (highest priority)
    try:
        if isinstance(target, Request):
            # Check canonical names first, then legacy names
            tok = (target.cookies.get(f"__Host-{GSNH_AT}") or
                   target.cookies.get(GSNH_AT) or
                   target.cookies.get(ACCESS_TOKEN))
            if tok:
                return ("access_cookie", tok)
        else:
            raw = target.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for p in parts:
                if (p.startswith(f"__Host-{GSNH_AT}=") or
                    p.startswith(f"{GSNH_AT}=") or
                    p.startswith(f"{ACCESS_TOKEN}=")):
                    return ("access_cookie", p.split("=", 1)[1])
    except Exception:
        pass
    # 2) Authorization header (second priority)
    try:
        auth = target.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            return ("authorization", auth.split(" ", 1)[1])
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
            # Standardized error shape for UI consistency
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "missing scope",
                    "hint": required,
                },
            )

    return _dep


def require_spotify_scope(required_scope: str = "user-read-private"):
    """Require specific Spotify scope for the request.

    This is a minimal hook for Spotify scope enforcement.
    Default scope is user-read-private which is commonly needed.
    """
    from fastapi import HTTPException

    def _dep(request: Request):
        payload = getattr(request.state, "jwt_payload", None)

        # Check if user has the required Spotify scope
        if not has_scope(payload, f"spotify:{required_scope}"):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "spotify_scope_required",
                    "message": f"Spotify scope '{required_scope}' required",
                    "hint": f"spotify:{required_scope}",
                },
            )

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

            raise HTTPException(status_code=400, detail="invalid_csrf")
    except Exception as e:
        # Be explicit: fail-closed for enabled CSRF on mutation
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="invalid_csrf")


__all__ = [
    "AuthConfig",
    "CFG",
    "decode_any",
    "decode_with_leeway",
    "validate_token_expiry",
    "get_token_expiry_info",
    "extract_token_metadata",
    "extract_token",
    "resolve_session_identity",
    "resolve_auth",
    "csrf_validate",
    "has_scope",
    "require_scope",
    "require_spotify_scope",
]

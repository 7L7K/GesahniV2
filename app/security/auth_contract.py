#!/usr/bin/env python3
"""
Authentication contract helpers and policy enforcement.

DoD (Auth):
- 401 from protected routes only when no valid auth at all (bearer or cookie)
- 403 when auth present but lacks scope (and scope is named in details)
- Cookies in prod: Secure, HttpOnly, SameSite=Strict
- Refresh returns {ok:true} plus re-set cookies; logout clears both cookies
- CSRF rule is consistent and documented in one place (this file)

CSRF Rule:
- Require X-CSRF-Token OR X-Requested-With on state-changing methods (POST/PUT/PATCH/DELETE)
- Unless endpoint is in explicit allowlist (OAuth callbacks, webhooks, file uploads)
- CSRF_ALLOWLIST_PATHS env var can list comma-separated paths to exempt

Bearer Precedence:
- Authorization: Bearer <token> overrides cookies when present
- Cookie-based access token (gsn_access) used when no bearer
- Session cookie (gsn_session) used for session-based auth
"""

import os
from typing import Any

from fastapi import HTTPException, Request

# Try to reuse existing project helpers when available
try:
    # Preferred: project-provided JWT decoding helper
    from app.security import decode_jwt  # type: ignore
except Exception:
    decode_jwt = None

try:
    # Cookie facade for canonical cookie reads
    from app.cookies import read_access_cookie, read_session_cookie
except Exception:
    # Fallback readers
    def read_access_cookie(request: Request) -> str | None:
        return request.cookies.get("gsn_access") or request.cookies.get("access_token")

    def read_session_cookie(request: Request) -> str | None:
        return request.cookies.get("gsn_session") or request.cookies.get("__session")


Identity = dict[str, Any]


def _decode_jwt(token: str) -> Identity | None:
    """Decode a JWT token into an identity dict, if possible.

    Prefers a project-level jwt_decode helper; otherwise uses PyJWT if available.
    Returns None on failure.
    """
    if not token:
        return None

    # Use project helper if present
    if decode_jwt is not None:
        try:
            # decode_jwt gets JWT secret from config internally
            return decode_jwt(token)
        except Exception:
            return None

    # Fallback to PyJWT
    try:
        import jwt

        secret = os.getenv("JWT_SECRET")
        leeway = int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60)
        if not secret:
            return None
        payload = jwt.decode(token, secret, algorithms=["HS256"], leeway=leeway)
        return dict(payload) if isinstance(payload, dict) else None
    except Exception:
        return None


def resolve_identity(request: Request) -> Identity | None:
    """Resolve caller identity from request.

    Precedence rules:
    - If an Authorization: Bearer <token> header is present and decodes to a valid JWT, use it.
    - Otherwise, if an access cookie is present and decodes to a valid JWT, use it.
    - Otherwise, if a session cookie is present, optionally resolve session identity (best-effort).

    This function never raises; it returns None when the caller is unauthenticated.
    """
    # 1) Bearer token precedence
    auth_hdr = request.headers.get("Authorization")
    if auth_hdr and auth_hdr.startswith("Bearer "):
        token = auth_hdr.split(" ", 1)[1].strip()
        ident = _decode_jwt(token)
        if ident:
            return ident

    # 2) Cookie-based access token
    access_cookie = read_access_cookie(request)
    if access_cookie:
        ident = _decode_jwt(access_cookie)
        if ident:
            return ident

    # 3) Session cookie (best-effort): may be resolved by session store elsewhere
    session_cookie = read_session_cookie(request)
    if session_cookie:
        # Prefer not to import heavy session store here to avoid cycles; return session id
        return {"session_id": session_cookie}

    return None


def require_auth(
    request: Request, required_scopes: list[str] | None = None
) -> Identity:
    """Require an authenticated identity for the request.

    Args:
        request: FastAPI request object
        required_scopes: List of required scopes. If provided, will raise 403
                        if identity lacks any required scope.

    Returns:
        Identity dict if authenticated and authorized

    Raises:
        HTTPException(401): When no valid auth at all (bearer or cookie)
        HTTPException(403): When auth present but lacks required scope(s)
    """
    ident = resolve_identity(request)
    if not ident:
        from app.http_errors import unauthorized

        raise unauthorized(code="not_authenticated", message="not authenticated")

    # Check scopes if required
    if required_scopes:
        missing_scopes = check_scopes(ident, required_scopes)
        if missing_scopes:
            raise HTTPException(
                status_code=403,
                detail=f"insufficient_scope: {', '.join(missing_scopes)}",
            )

    return ident


def check_scopes(identity: Identity, required_scopes: list[str]) -> list[str]:
    """Check if identity has all required scopes.

    Args:
        identity: Identity dict from JWT or session
        required_scopes: List of required scope strings

    Returns:
        List of missing scope names (empty if all scopes present)
    """
    if not identity or not isinstance(identity, dict):
        return required_scopes.copy()

    # Extract scopes from identity (JWT 'scope' claim or 'scopes' key)
    identity_scopes = set()
    if "scope" in identity:
        scope_str = identity["scope"]
        if isinstance(scope_str, str):
            identity_scopes.update(s.strip() for s in scope_str.split())
        elif isinstance(scope_str, list):
            identity_scopes.update(str(s).strip() for s in scope_str)

    if "scopes" in identity:
        scopes_list = identity["scopes"]
        if isinstance(scopes_list, list):
            identity_scopes.update(str(s).strip() for s in scopes_list)

    # Check for missing scopes
    missing = []
    for scope in required_scopes:
        if scope not in identity_scopes:
            missing.append(scope)

    return missing


def has_scope(identity: Identity, scope: str) -> bool:
    """Check if identity has a specific scope.

    Args:
        identity: Identity dict from JWT or session
        scope: Required scope string

    Returns:
        True if identity has the scope
    """
    return len(check_scopes(identity, [scope])) == 0


def require_csrf(request: Request) -> None:
    """Require CSRF protection for state-changing requests.

    Enforces X-CSRF-Token OR X-Requested-With on POST/PUT/PATCH/DELETE methods,
    unless the endpoint is in the CSRF allowlist.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException(400): When CSRF token is missing or invalid
    """
    # Skip CSRF check for safe methods
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return

    # Check if path is in allowlist
    path = request.url.path
    allowlist = _get_csrf_allowlist()
    if any(allowed_path in path for allowed_path in allowlist):
        return

    # Require X-CSRF-Token OR X-Requested-With
    csrf_token = request.headers.get("X-CSRF-Token")
    requested_with = request.headers.get("X-Requested-With")

    if not csrf_token and not requested_with:
        raise HTTPException(status_code=400, detail="csrf.missing")

    # If X-CSRF-Token is provided, validate it against cookie
    if csrf_token:
        csrf_cookie = request.cookies.get("csrf_token")
        if not csrf_cookie or csrf_token != csrf_cookie:
            raise HTTPException(status_code=400, detail="csrf.invalid")


def _get_csrf_allowlist() -> list[str]:
    """Get list of paths exempt from CSRF protection."""
    allowlist_str = os.getenv("CSRF_ALLOWLIST_PATHS", "")
    if not allowlist_str:
        return [
            "/v1/auth/google/callback",  # OAuth callbacks
            "/v1/auth/apple/callback",
            "/auth/google/callback",
            "/auth/apple/callback",
            "/v1/ha/webhook",  # Webhooks
            "/ha/webhook",
            "/v1/upload",  # File uploads
            "/upload",
        ]

    return [path.strip() for path in allowlist_str.split(",") if path.strip()]


# Export convenience
__all__ = [
    "resolve_identity",
    "require_auth",
    "check_scopes",
    "has_scope",
    "require_csrf",
]

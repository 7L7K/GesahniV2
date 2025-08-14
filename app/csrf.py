from __future__ import annotations

import os
from fastapi import Request, Response
from secrets import token_urlsafe
from starlette.middleware.base import BaseHTTPMiddleware


def _truthy(env_val: str | None) -> bool:
    if env_val is None:
        return False
    return str(env_val).strip().lower() in {"1", "true", "yes", "on"}


def _extract_csrf_header(request: Request) -> tuple[str | None, bool, bool]:
    """Return (token, used_legacy, legacy_allowed).

    - Prefer X-CSRF-Token
    - Accept legacy X-CSRF only when CSRF_LEGACY_GRACE is truthy
    - Emit a warning via print when legacy is used and allowed
    """
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token, False, False
    legacy = request.headers.get("X-CSRF")
    if legacy:
        allowed = _truthy(os.getenv("CSRF_LEGACY_GRACE", "1"))
        if allowed:
            try:
                # Log with explicit deprecation date for ops visibility
                print("csrf.legacy_header used removal=2025-12-31")
            except Exception:
                pass
        return legacy, True, allowed
    return None, False, False


class CSRFMiddleware(BaseHTTPMiddleware):
    """Simple double-submit CSRF.

    - Allow safe methods (GET/HEAD/OPTIONS).
    - For POST/PUT/PATCH/DELETE, require header X-CSRF-Token to match cookie csrf_token.
    - Disabled when CSRF_ENABLED=0.
    """

    async def dispatch(self, request: Request, call_next):
        # Default disabled globally; enable per app/env via CSRF_ENABLED=1
        if not _truthy(os.getenv("CSRF_ENABLED", "0")):
            return await call_next(request)
        if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        token_hdr, used_legacy, legacy_allowed = _extract_csrf_header(request)
        token_cookie = request.cookies.get("csrf_token") or ""
        # Reject legacy header when grace disabled
        if used_legacy and not legacy_allowed:
            return Response(status_code=400)
        # Require both header and cookie, and match
        if not token_hdr or not token_cookie:
            return Response(status_code=403)
        if token_hdr != token_cookie:
            return Response(status_code=403)
        return await call_next(request)


async def get_csrf_token() -> str:
    """Return an existing csrf_token cookie or mint a new random value.

    Middlewares that want to ensure presence can call this and set cookie.
    The /v1/csrf endpoint returns this value for test flows.
    """
    # For now, just return a random per-call token; a route should set cookie.
    return token_urlsafe(16)


__all__ = ["CSRFMiddleware", "get_csrf_token", "_extract_csrf_header"]



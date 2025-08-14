from __future__ import annotations

import os
from fastapi import Request, Response
from secrets import token_urlsafe
from starlette.middleware.base import BaseHTTPMiddleware


class CSRFMiddleware(BaseHTTPMiddleware):
    """Simple double-submit CSRF.

    - Allow safe methods (GET/HEAD/OPTIONS).
    - For POST/PUT/PATCH/DELETE, require header X-CSRF-Token to match cookie csrf_token.
    - Disabled when CSRF_ENABLED=0.
    """

    async def dispatch(self, request: Request, call_next):
        # Default disabled globally; enable per app/env via CSRF_ENABLED=1
        if os.getenv("CSRF_ENABLED", "0").lower() not in {"1", "true", "yes", "on"}:
            return await call_next(request)
        if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        token_hdr = request.headers.get("X-CSRF-Token") or ""
        token_cookie = request.cookies.get("csrf_token") or ""
        if not token_hdr or token_hdr != token_cookie:
            return Response(status_code=403)
        return await call_next(request)


async def get_csrf_token() -> str:
    """Return an existing csrf_token cookie or mint a new random value.

    Middlewares that want to ensure presence can call this and set cookie.
    The /v1/csrf endpoint returns this value for test flows.
    """
    # For now, just return a random per-call token; a route should set cookie.
    return token_urlsafe(16)


__all__ = ["CSRFMiddleware", "get_csrf_token"]



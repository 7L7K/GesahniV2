from __future__ import annotations

import os
from fastapi import Request, Response
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


__all__ = ["CSRFMiddleware"]



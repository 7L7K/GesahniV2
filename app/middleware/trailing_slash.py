"""Trailing Slash Middleware for consistent URL handling.

This middleware enforces a strict trailing slash policy:
- All URLs should end without a trailing slash (canonical form)
- URLs with trailing slashes are redirected to the canonical form with 308 status
- Preserves query parameters and fragments
"""

from __future__ import annotations

import re
from typing import Pattern

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


class TrailingSlashMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces consistent trailing slash policy."""

    def __init__(self, app):
        super().__init__(app)
        
        # Patterns for routes that should NOT be redirected (exceptions)
        self.no_redirect_patterns: list[Pattern[str]] = [
            # Root path
            re.compile(r"^/$"),
            
            # Health endpoints (these might be hit by load balancers with trailing slashes)
            re.compile(r"^/health$"),
            re.compile(r"^/healthz"),
            re.compile(r"^/livez$"),
            re.compile(r"^/readyz$"),
            
            # Metrics and monitoring
            re.compile(r"^/metrics"),
            
            # Static files (if any)
            re.compile(r"^/static/"),
            
            # OpenAPI docs (these might use trailing slashes)
            re.compile(r"^/docs"),
            re.compile(r"^/redoc"),
            re.compile(r"^/openapi\.json"),
        ]

    async def dispatch(self, request: Request, call_next):
        """Process request and redirect trailing slash URLs to canonical form."""
        path = request.url.path
        
        # Skip if path doesn't end with trailing slash
        if not path.endswith('/'):
            return await call_next(request)
        
        # Skip if path is just "/" (root)
        if path == '/':
            return await call_next(request)
        
        # Check if this path should be excluded from redirect
        if any(pattern.match(path) for pattern in self.no_redirect_patterns):
            return await call_next(request)
        
        # Build canonical URL (remove trailing slash)
        canonical_path = path.rstrip('/')
        
        # Preserve query parameters (fragments are not sent to server in Location headers)
        query_string = request.url.query
        
        canonical_url = canonical_path
        if query_string:
            canonical_url += f"?{query_string}"
        
        # Return 308 Permanent Redirect to canonical form
        # 308 preserves the HTTP method (important for POST/PUT requests)
        return RedirectResponse(url=canonical_url, status_code=308)

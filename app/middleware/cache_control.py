"""Cache Control Middleware for consistent cache headers across all routes.

This middleware ensures proper cache-control headers are set based on route patterns:
- Auth-bearing or dynamic routes: Cache-Control: no-store, Pragma: no-cache, Expires: 0
- Safe static/config/debug routes: private, max-age=30 (if truly safe)
- Health endpoints: no-store (already handled in health.py)
"""

from __future__ import annotations

import re
from typing import Pattern

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Middleware that sets appropriate cache-control headers based on route patterns."""

    def __init__(self, app):
        super().__init__(app)
        
        # Patterns for routes that should never be cached (auth-bearing, dynamic, user-specific)
        self.no_cache_patterns: list[Pattern[str]] = [
            # Auth endpoints
            re.compile(r"^/v1/auth/"),
            re.compile(r"^/auth/"),
            re.compile(r"^/login"),
            re.compile(r"^/logout"),
            re.compile(r"^/register"),
            re.compile(r"^/refresh"),
            
            # User-specific endpoints
            re.compile(r"^/v1/me"),
            re.compile(r"^/v1/profile"),
            re.compile(r"^/v1/sessions"),
            re.compile(r"^/v1/pats"),
            
            # Dynamic content endpoints
            re.compile(r"^/v1/ask"),
            re.compile(r"^/ask"),
            re.compile(r"^/v1/chat"),
            
            # Spotify/user-specific music endpoints
            re.compile(r"^/v1/spotify/"),
            re.compile(r"^/v1/music/"),
            
            # Admin endpoints (sensitive)
            re.compile(r"^/v1/admin/"),
            re.compile(r"^/admin/"),
            
            # WebSocket endpoints
            re.compile(r"^/v1/ws/"),
            
            # Any endpoint with user ID or session in path
            re.compile(r"/users/"),
            re.compile(r"/sessions/"),
        ]
        
        # Patterns for routes that might be safely cached for short periods
        self.safe_cache_patterns: list[Pattern[str]] = [
            # Health endpoints (but these already set no-store in health.py)
            re.compile(r"^/health"),
            re.compile(r"^/healthz"),
            re.compile(r"^/livez"),
            re.compile(r"^/readyz"),
            
            # Static config endpoints (if truly static)
            re.compile(r"^/v1/config$"),  # Only exact match, not subpaths
            re.compile(r"^/config$"),
            
            # Public status endpoints (if truly public)
            re.compile(r"^/v1/status$"),  # Only exact match
            re.compile(r"^/status$"),
            
            # Debug endpoints (development only)
            re.compile(r"^/debug/"),
            re.compile(r"^/v1/debug/"),
        ]

    async def dispatch(self, request: Request, call_next):
        """Process request and set appropriate cache-control headers."""
        response = await call_next(request)
        
        # Only set headers on successful responses
        if response.status_code >= 200 and response.status_code < 300:
            path = request.url.path
            
            # Check if this route should never be cached
            should_no_cache = any(pattern.match(path) for pattern in self.no_cache_patterns)
            
            if should_no_cache:
                # Auth-bearing or dynamic routes: aggressive no-cache
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                
            elif any(pattern.match(path) for pattern in self.safe_cache_patterns):
                # Safe static/config/debug routes: short private cache
                # Only cache if no user-specific headers are present
                if not self._has_user_specific_headers(request):
                    response.headers.setdefault("Cache-Control", "private, max-age=30")
                    response.headers.setdefault("Vary", "Accept, Authorization, Cookie")
            else:
                # Default: no cache for unknown routes
                response.headers.setdefault("Cache-Control", "no-store")
                response.headers.setdefault("Pragma", "no-cache")
        
        return response

    def _has_user_specific_headers(self, request: Request) -> bool:
        """Check if request has user-specific headers that should prevent caching."""
        user_headers = [
            "authorization",
            "cookie",
            "x-csrf-token",
            "x-request-id",  # Often user-specific
        ]
        
        for header_name in user_headers:
            if header_name in request.headers:
                return True
        return False

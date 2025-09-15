"""
CORS middleware module for GesahniV2.

This module provides CORS middleware functionality including origin validation,
preflight handling, and metrics collection for CORS-related security events.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..settings_cors import get_cors_origins

logger = logging.getLogger(__name__)

# Global metrics for CORS rejection tracking
_cors_rejected_count = 0
_cors_rejected_origins = set()


def _is_production_mode() -> bool:
    """Check if the application is running in production mode."""
    # Check ENV=prod first
    env = os.getenv("ENV", "dev").strip().lower()
    if env == "prod":
        return True

    # Also check PRODUCTION=1 for backward compatibility
    production = os.getenv("PRODUCTION", "").strip()
    return production == "1"


def _get_allowed_origins() -> list[str]:
    """Get the list of allowed CORS origins."""
    return get_cors_origins()


def _get_preflight_max_age() -> int:
    """Get the max age for CORS preflight caching."""
    from .settings_cors import get_cors_max_age

    return get_cors_max_age()


def get_cors_metrics() -> dict[str, Any]:
    """Get CORS-related metrics for monitoring."""
    return {
        "cors_rejected_count": _cors_rejected_count,
        "cors_rejected_origins": list(_cors_rejected_origins),
        "cors_allowed_origins": _get_allowed_origins(),
    }


class CorsMiddleware(BaseHTTPMiddleware):
    """CORS middleware for handling cross-origin requests.

    Validates origins, handles preflight requests, and tracks rejection metrics.
    """

    def __init__(self, app: Any, **options: Any):
        super().__init__(app)
        self.options = options

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process the request and handle CORS headers."""
        global _cors_rejected_count

        # Get the origin from the request
        origin = request.headers.get("origin", "")

        # Check if origin is allowed
        allowed_origins = _get_allowed_origins()
        is_allowed = not origin or origin in allowed_origins

        # Handle CORS preflight requests
        if request.method == "OPTIONS":
            response = Response()
            if not is_allowed:
                _cors_rejected_count += 1
                _cors_rejected_origins.add(origin)
                logger.warning(f"CORS preflight rejected for origin: {origin}")
                response.status_code = 403
                return response

            # Add CORS headers for allowed requests
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = "*, Authorization"
            response.headers["Access-Control-Expose-Headers"] = (
                "X-Request-ID, X-Error-Code, X-Error-ID, X-Trace-ID"
            )
            response.headers["Access-Control-Max-Age"] = str(_get_preflight_max_age())
            return response

        # Process the request
        response = await call_next(request)

        # Add CORS headers to the response for allowed origins
        if is_allowed:
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
            else:
                response.headers["Access-Control-Allow-Origin"] = "*"

        return response


class CorsPreflightMiddleware(BaseHTTPMiddleware):
    """Middleware specifically for handling CORS preflight OPTIONS requests."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Handle preflight OPTIONS requests."""
        if request.method == "OPTIONS":
            return await CorsMiddleware(None).dispatch(request, call_next)
        return await call_next(request)

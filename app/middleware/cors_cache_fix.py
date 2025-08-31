"""
Safari CORS Cache Fix Middleware

This middleware adds cache control headers to CORS responses to prevent
Safari from aggressively caching CORS preflight responses.

Safari is known to cache CORS failures and continue blocking requests even
after the server configuration is fixed. This middleware adds no-cache headers
to all CORS-related responses to prevent this issue.
"""

import logging
from typing import List, Optional, Sequence

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SafariCORSCacheFixMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds cache control headers to CORS responses to prevent Safari caching.

    This middleware should be placed AFTER the CORSMiddleware in the middleware stack.
    It detects CORS responses and adds cache control headers to prevent Safari from
    caching preflight responses.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Process the request normally
        response = await call_next(request)

        # Check if this is a CORS-related response
        has_cors_headers = any(
            header.lower().startswith("access-control-")
            for header in response.headers.keys()
        )

        # Add cache control headers for CORS responses or OPTIONS requests
        if has_cors_headers or request.method == "OPTIONS":
            # Add headers to prevent caching of CORS responses
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

            # Enhance Vary header to include all headers that affect CORS
            vary_headers = set()
            if "Vary" in response.headers:
                vary_headers.update(h.strip() for h in response.headers["Vary"].split(","))

            # Add CORS-relevant headers to Vary
            cors_vary_headers = [
                "Origin",
                "Access-Control-Request-Method",
                "Access-Control-Request-Headers",
                "Authorization"
            ]
            vary_headers.update(cors_vary_headers)

            response.headers["Vary"] = ", ".join(sorted(vary_headers))

            logger.debug(
                "Safari CORS cache fix applied",
                extra={
                    "meta": {
                        "method": request.method,
                        "path": request.url.path,
                        "has_cors_headers": has_cors_headers,
                        "is_preflight": request.method == "OPTIONS",
                    }
                }
            )

        return response

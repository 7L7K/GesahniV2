"""
CORS middleware implementation for GesahniV2.

This module provides CORS handling separate from cookies/auth.
Handles preflight requests, credentials, and origin validation.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Set

from fastapi import Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CorsMiddleware(BaseHTTPMiddleware):
    """Custom CORS middleware implementation.

    Handles preflight OPTIONS requests and adds appropriate CORS headers.
    Validates origins and manages credentials handling.
    """

    def __init__(
        self,
        app,
        allow_origins: List[str] | None = None,
        allow_credentials: bool = True,
        allow_methods: List[str] | None = None,
        allow_headers: List[str] | None = None,
        expose_headers: List[str] | None = None,
        max_age: int = 600,
    ):
        super().__init__(app)
        self.allow_origins = set(allow_origins or [])
        self.allow_credentials = allow_credentials
        self.allow_methods = set(allow_methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
        self.allow_headers = set(allow_headers or ["*"])
        self.expose_headers = expose_headers or ["X-Request-ID", "X-Error-Code", "X-Error-ID", "X-Trace-ID"]
        self.max_age = max_age

    async def dispatch(self, request: Request, call_next):
        # Get the request origin
        origin = request.headers.get("Origin")

        # Check if this is a CORS request
        is_cors_request = origin is not None

        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS" and is_cors_request:
            return await self._handle_preflight(request, origin)

        # Process the request
        response = await call_next(request)

        # Add CORS headers to the response if it's a CORS request
        if is_cors_request:
            response = await self._add_cors_headers(response, origin, request.method)

        return response

    async def _handle_preflight(self, request: Request, origin: str) -> Response:
        """Handle CORS preflight OPTIONS requests."""

        # Validate origin
        if not self._is_origin_allowed(origin):
            logger.warning("cors_preflight_rejected origin=<%s>", origin)
            return Response(status_code=400, content="Invalid origin")

        # Check requested method
        requested_method = request.headers.get("Access-Control-Request-Method", "")
        if requested_method and requested_method.upper() not in self.allow_methods:
            logger.warning(
                "cors_preflight_rejected_method method=<%s> allowed=%s",
                requested_method,
                list(self.allow_methods)
            )
            return Response(status_code=400, content="Method not allowed")

        # Check requested headers
        requested_headers = request.headers.get("Access-Control-Request-Headers", "")
        if requested_headers:
            headers_list = [h.strip() for h in requested_headers.split(",")]
            for header in headers_list:
                if header not in self.allow_headers and "*" not in self.allow_headers:
                    logger.warning(
                        "cors_preflight_rejected_header header=<%s> allowed=%s",
                        header,
                        list(self.allow_headers)
                    )
                    return Response(status_code=400, content="Header not allowed")

        # Create preflight response
        response = Response(status_code=200)

        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = origin
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = ", ".join(sorted(self.allow_methods))
        response.headers["Access-Control-Allow-Headers"] = ", ".join(sorted(self.allow_headers))
        response.headers["Access-Control-Max-Age"] = str(self.max_age)

        logger.info("cors_preflight_allowed origin=<%s>", origin)
        return response

    async def _add_cors_headers(self, response: Response, origin: str, method: str) -> Response:
        """Add CORS headers to a regular response."""

        # Validate origin
        if not self._is_origin_allowed(origin):
            # For non-preflight requests with invalid origin, don't add CORS headers
            # This prevents leaking CORS info to potentially malicious origins
            logger.warning("cors_request_rejected origin=<%s>", origin)
            return response

        # Add basic CORS headers
        response.headers["Access-Control-Allow-Origin"] = origin

        # Add credentials header if allowed
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        # Add exposed headers if any
        if self.expose_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)

        # For error responses, ensure CORS headers are still present
        if response.status_code >= 400:
            logger.info(
                "cors_error_headers_added origin=<%s> status=%d",
                origin,
                response.status_code
            )

        return response

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if the given origin is allowed."""
        if not self.allow_origins:
            # If no origins specified, allow localhost variants by default
            return self._is_localhost_origin(origin)

        # Check exact matches
        if origin in self.allow_origins:
            return True

        # Check localhost variants
        if self._is_localhost_origin(origin):
            # Allow localhost variants if any localhost origin is configured
            for allowed_origin in self.allow_origins:
                if "localhost" in allowed_origin or "127.0.0.1" in allowed_origin:
                    return True

        return False

    def _is_localhost_origin(self, origin: str) -> bool:
        """Check if origin is a localhost variant."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            hostname = parsed.hostname

            # Allow localhost and 127.0.0.1 variants
            if hostname in ("localhost", "127.0.0.1"):
                return True

            # Allow localhost with different ports
            if hostname == "localhost":
                return True

        except Exception:
            pass

        return False


class CorsPreflightMiddleware(BaseHTTPMiddleware):
    """Handle CORS preflight OPTIONS requests before other middleware."""

    async def dispatch(self, request: Request, call_next):
        """Handle CORS preflight OPTIONS requests."""
        # Check if this is an OPTIONS request with Origin header
        if request.method.upper() == "OPTIONS" and request.headers.get("Origin"):
            # Create CORS headers
            cors_headers = {}
            origin = request.headers.get("Origin")

            # Add basic CORS headers
            if origin:
                cors_headers["Access-Control-Allow-Origin"] = origin
                cors_headers["Access-Control-Allow-Credentials"] = "true"
                cors_headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                cors_headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,X-CSRF-Token"
                cors_headers["Vary"] = "Origin"

                # Add max-age for caching
                cors_headers["Access-Control-Max-Age"] = "600"

            # Return 200 OK for preflight requests (matches FastAPI CORS middleware behavior)
            return PlainTextResponse("", status_code=200, headers=cors_headers)

        # Continue with normal request processing
        return await call_next(request)


__all__ = ["CorsMiddleware", "CorsPreflightMiddleware"]

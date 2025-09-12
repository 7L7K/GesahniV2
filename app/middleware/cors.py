"""
CORS middleware implementation for GesahniV2.

This module provides CORS handling separate from cookies/auth.
Handles preflight requests, credentials, and origin validation.

PRODUCTION FEATURES:
- Explicit origin allowlist enforcement (no wildcards in prod)
- Preflight cache tuning (Access-Control-Max-Age)
- Debug metrics for rejected origins
- Environment-based configuration
"""

from __future__ import annotations

import logging
import os

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Production CORS metrics
_cors_rejected_origins = set()
_cors_rejected_count = 0


def get_cors_metrics():
    """Get CORS rejection metrics for monitoring."""
    return {
        "rejected_origins": list(_cors_rejected_origins),
        "rejected_count": _cors_rejected_count
    }


def _is_production_mode():
    """Check if running in production mode."""
    return os.getenv("ENV", "").lower() in {"prod", "production"} or os.getenv("PRODUCTION", "0") == "1"


def _get_allowed_origins():
    """Get allowed origins from environment with production validation."""
    origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()

    if not origins_raw:
        # Default localhost variants for development
        if not _is_production_mode():
            return {"http://localhost:3000", "http://127.0.0.1:3000"}
        else:
            logger.warning("CORS_ALLOW_ORIGINS not set in production - no origins allowed")
            return set()

    origins = set()
    for origin in origins_raw.split(","):
        origin = origin.strip()
        if not origin:
            continue

        # Production validation: no wildcards allowed
        if _is_production_mode():
            if "*" in origin:
                logger.error(f"Wildcard origin '{origin}' not allowed in production")
                continue
            if not origin.startswith(("http://", "https://")):
                logger.error(f"Origin '{origin}' must use http:// or https:// in production")
                continue

        origins.add(origin)

    return origins


def _get_preflight_max_age():
    """Get preflight cache duration from environment."""
    default = 600 if not _is_production_mode() else 3600  # 10min dev, 1hr prod
    return int(os.getenv("CORS_MAX_AGE", str(default)))


class CorsMiddleware(BaseHTTPMiddleware):
    """Production-ready CORS middleware with allowlist enforcement.

    Features:
    - Explicit origin allowlist (no wildcards in production)
    - Configurable preflight cache duration
    - Rejection metrics for monitoring
    - Environment-based configuration
    """

    def __init__(
        self,
        app,
        allow_origins: list[str] | None = None,
        allow_credentials: bool = True,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        expose_headers: list[str] | None = None,
        max_age: int | None = None,
    ):
        super().__init__(app)

        # Use environment config if no explicit origins provided
        if allow_origins is None:
            self.allow_origins = _get_allowed_origins()
        else:
            self.allow_origins = set(allow_origins)

        self.allow_credentials = allow_credentials
        self.allow_methods = set(allow_methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
        self.allow_headers = set(allow_headers or ["Authorization", "Content-Type", "X-CSRF-Token"])
        self.expose_headers = expose_headers or ["X-Request-ID", "X-Error-Code", "X-Error-ID", "X-Trace-ID"]

        # Use environment max_age if not provided
        self.max_age = max_age if max_age is not None else _get_preflight_max_age()

        logger.info(
            "cors.middleware_initialized",
            extra={
                "meta": {
                    "origins_count": len(self.allow_origins),
                    "production_mode": _is_production_mode(),
                    "max_age": self.max_age,
                    "allow_credentials": self.allow_credentials
                }
            }
        )

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
        """Handle CORS preflight OPTIONS requests with production validation."""

        # Validate origin
        if not self._is_origin_allowed(origin):
            global _cors_rejected_origins, _cors_rejected_count
            _cors_rejected_origins.add(origin)
            _cors_rejected_count += 1

            logger.warning(
                "cors_preflight_rejected origin=<%s> allowed=%s production=%s",
                origin,
                list(self.allow_origins),
                _is_production_mode()
            )
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
        """Add CORS headers to a regular response with production validation."""

        # Validate origin
        if not self._is_origin_allowed(origin):
            global _cors_rejected_origins, _cors_rejected_count
            _cors_rejected_origins.add(origin)
            _cors_rejected_count += 1

            # For non-preflight requests with invalid origin, don't add CORS headers
            # This prevents leaking CORS info to potentially malicious origins
            logger.warning(
                "cors_request_rejected origin=<%s> method=<%s> production=%s",
                origin,
                method,
                _is_production_mode()
            )
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
        """Check if the given origin is allowed with production validation."""
        # Check exact matches first
        if origin in self.allow_origins:
            return True

        # In production, only exact matches are allowed
        if _is_production_mode():
            return False

        # Development: allow localhost variants
        if self._is_localhost_origin(origin):
            return True

        return False

    def _is_localhost_origin(self, origin: str) -> bool:
        """Check if origin is a localhost variant (development only)."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            hostname = parsed.hostname

            # Allow localhost and 127.0.0.1 variants
            if hostname in ("localhost", "127.0.0.1"):
                return True

        except Exception:
            pass

        return False


class CorsPreflightMiddleware(BaseHTTPMiddleware):
    """Production-ready CORS preflight middleware with allowlist enforcement and metrics."""

    def __init__(self, app, allow_origins: list[str] | None = None, **kwargs):
        super().__init__(app)

        # Use environment config if no explicit origins provided
        if allow_origins is None:
            self.allow_origins = _get_allowed_origins()
        else:
            self.allow_origins = set(allow_origins)

        self.max_age = _get_preflight_max_age()

        logger.info(
            "cors.preflight_middleware_initialized",
            extra={
                "meta": {
                    "origins_count": len(self.allow_origins),
                    "production_mode": _is_production_mode(),
                    "max_age": self.max_age
                }
            }
        )

    async def dispatch(self, request: Request, call_next):
        """Handle CORS preflight OPTIONS requests with production validation."""
        # Check if this is an OPTIONS request with Origin header
        if request.method.upper() == "OPTIONS" and request.headers.get("Origin"):
            origin = request.headers.get("Origin")

            # Validate origin
            if origin and not self._is_origin_allowed(origin):
                global _cors_rejected_origins, _cors_rejected_count
                _cors_rejected_origins.add(origin)
                _cors_rejected_count += 1

                logger.warning(
                    "cors_preflight_rejected origin=<%s> allowed=%s production=%s",
                    origin,
                    list(self.allow_origins),
                    _is_production_mode()
                )
                return Response(status_code=400, content="Invalid origin")

            # Create CORS headers
            cors_headers = {}

            # Add basic CORS headers
            if origin:
                cors_headers["Access-Control-Allow-Origin"] = origin
                cors_headers["Access-Control-Allow-Credentials"] = "true"
                cors_headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                cors_headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type,X-CSRF-Token"
                cors_headers["Vary"] = "Origin"

                # Add max-age for caching (production-tuned)
                cors_headers["Access-Control-Max-Age"] = str(self.max_age)

            # Return 200 OK for preflight requests (matches FastAPI CORS middleware behavior)
            return PlainTextResponse("", status_code=200, headers=cors_headers)

        # Continue with normal request processing
        return await call_next(request)

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if the given origin is allowed with production validation."""
        # Check exact matches first
        if origin in self.allow_origins:
            return True

        # In production, only exact matches are allowed
        if _is_production_mode():
            return False

        # Development: allow localhost variants
        if self._is_localhost_origin(origin):
            return True

        return False

    def _is_localhost_origin(self, origin: str) -> bool:
        """Check if origin is a localhost variant (development only)."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            hostname = parsed.hostname

            # Allow localhost and 127.0.0.1 variants
            if hostname in ("localhost", "127.0.0.1"):
                return True

        except Exception:
            pass

        return False


__all__ = ["CorsMiddleware", "CorsPreflightMiddleware"]

"""
Phase 6.1: Metrics Middleware

Clean Prometheus metrics collection for HTTP requests.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.metrics import LATENCY, REQUESTS


def _route_name(scope) -> str:
    """Extract route name from request scope."""
    endpoint = scope.get("endpoint")
    if endpoint and hasattr(endpoint, "__name__"):
        return endpoint.__name__

    # fallback to path template if available
    path = scope.get("path", "<unknown>")
    # Clean up path for metrics - remove leading /v1 and common patterns
    if path.startswith("/v1/"):
        path = path[3:]  # Remove /v1 prefix
    elif path.startswith("/health") or path.startswith("/metrics"):
        return path  # Keep health/metrics as-is

    return path or "<unknown>"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Clean metrics collection middleware for HTTP requests."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        route = _route_name(request.scope)
        method = request.method.upper()
        status = 500  # Default to server error

        try:
            resp: Response = await call_next(request)
            status = getattr(resp, "status_code", 200)
            return resp
        except Exception:
            # Exception occurred, will be handled by error middleware
            status = 500
            raise
        finally:
            # Always record metrics even if response is None (error case)
            duration = time.perf_counter() - start

            # Record metrics
            REQUESTS.labels(route=route, method=method, status=str(status)).inc()
            LATENCY.labels(route=route, method=method).observe(duration)

"""Reusable helper for creating legacy route aliases with tracking.

This module provides a generic legacy_alias function that wraps canonical handlers
with deprecation headers, structured logging, and Prometheus metrics tracking.
"""

import logging
from collections.abc import Callable
from typing import Any

try:
    from prometheus_client import Counter

    AUTH_LEGACY_HITS_TOTAL = Counter(
        "auth_legacy_hits_total", "Total hits on legacy auth endpoints", ["endpoint"]
    )
except ImportError:
    # Fallback for when prometheus is not available
    class _StubCounter:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

    AUTH_LEGACY_HITS_TOTAL = _StubCounter()

logger = logging.getLogger(__name__)

# Sunset date for legacy auth routes (Wed, 31 Dec 2025 23:59:59 GMT)
SUNSET_DATE_RFC7231 = "Wed, 31 Dec 2025 23:59:59 GMT"


class LegacyAlias:
    """Class-based decorator that preserves function signatures for FastAPI."""

    def __init__(
        self, path: str, successor: str, method: str, handler: Callable[..., Any]
    ):
        self.path = path
        self.successor = successor
        self.method = method
        self.handler = handler

        # Preserve original function metadata
        self.__name__ = handler.__name__
        self.__doc__ = handler.__doc__
        self.__annotations__ = getattr(handler, "__annotations__", {})

    async def __call__(self, *args, **kwargs):
        # Increment Prometheus counter
        AUTH_LEGACY_HITS_TOTAL.labels(endpoint=self.path).inc()

        # Log structured warning
        logger.warning(
            "LEGACY_ROUTE_USED",
            extra={
                "endpoint": self.path,
                "successor": self.successor,
                "sunset": "2025-12-31",
                "method": self.method,
            },
        )

        # Call the canonical handler
        result = await self.handler(*args, **kwargs)

        # Add deprecation headers if result has headers
        if hasattr(result, "headers"):
            result.headers.setdefault("Deprecation", "true")
            result.headers.setdefault("Sunset", SUNSET_DATE_RFC7231)
            result.headers.setdefault(
                "Link", f'<{self.successor}>; rel="successor-version"'
            )

        return result


def legacy_alias(
    path: str, successor: str, method: str, handler: Callable[..., Any]
) -> LegacyAlias:
    """Wrap a canonical handler to provide a legacy alias with tracking.

    Args:
        path: The legacy endpoint path (e.g., "/v1/login")
        successor: The canonical endpoint path (e.g., "/v1/auth/login")
        method: The HTTP method (e.g., "POST", "GET")
        handler: The canonical handler function to delegate to

    Returns:
        A LegacyAlias instance that wraps the handler with tracking
    """
    return LegacyAlias(path, successor, method, handler)

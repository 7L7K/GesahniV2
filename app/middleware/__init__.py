# app/middleware/__init__.py
"""
Application middleware modules.

This package contains middleware components for request processing,
rate limiting, session management, and observability.
"""

# Strict re-exports to avoid circular imports and None values
from .custom import (
    EnhancedErrorHandlingMiddleware,
    ReloadEnvMiddleware,
    SilentRefreshMiddleware,
)
from .loader import add_mw
from .middleware_core import (
    DedupMiddleware,
    HealthCheckFilterMiddleware,
    RedactHashMiddleware,
    RequestIDMiddleware,
    TraceRequestMiddleware,
    reload_env_middleware,
    silent_refresh_middleware,
)
from .rate_limit import RateLimitMiddleware
from .session_attach import SessionAttachMiddleware

__all__ = [
    "RequestIDMiddleware",
    "DedupMiddleware",
    "TraceRequestMiddleware",
    "HealthCheckFilterMiddleware",
    "RedactHashMiddleware",
    "RateLimitMiddleware",
    "SessionAttachMiddleware",
    "EnhancedErrorHandlingMiddleware",
    "SilentRefreshMiddleware",
    "ReloadEnvMiddleware",
    "reload_env_middleware",
    "silent_refresh_middleware",
    "add_mw",
]

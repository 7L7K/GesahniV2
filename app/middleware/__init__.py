# app/middleware/__init__.py
"""
Application middleware modules.

This package contains middleware components for request processing,
rate limiting, session management, and observability.
"""

# Strict re-exports to avoid circular imports and None values
from .audit_mw import AuditMiddleware
from .cors_cache_fix import SafariCORSCacheFixMiddleware
from ..csrf import CSRFMiddleware
from .custom import (
    EnhancedErrorHandlingMiddleware,
    ReloadEnvMiddleware,
    SilentRefreshMiddleware,
)
from .error_handler import ErrorHandlerMiddleware
from .loader import add_mw
from .metrics_mw import MetricsMiddleware
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
    "AuditMiddleware",
    "RequestIDMiddleware",
    "DedupMiddleware",
    "TraceRequestMiddleware",
    "HealthCheckFilterMiddleware",
    "RedactHashMiddleware",
    "MetricsMiddleware",
    "RateLimitMiddleware",
    "SessionAttachMiddleware",
    "CSRFMiddleware",
    "ErrorHandlerMiddleware",
    "EnhancedErrorHandlingMiddleware",
    "SilentRefreshMiddleware",
    "ReloadEnvMiddleware",
    "SafariCORSCacheFixMiddleware",
    "reload_env_middleware",
    "silent_refresh_middleware",
    "add_mw",
]

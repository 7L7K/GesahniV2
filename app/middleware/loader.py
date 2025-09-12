"""
Deterministic middleware loader with validation.

This module provides a safe wrapper around app.add_middleware that validates
middleware classes at startup and fails loudly if anything is wrong.
"""

import inspect
import logging
import os

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from ..csrf import CSRFMiddleware

# Import middleware classes directly to avoid circular imports
from .audit_mw import AuditMiddleware
from .cors import CorsPreflightMiddleware
from .cors_cache_fix import SafariCORSCacheFixMiddleware
from .custom import (
    EnhancedErrorHandlingMiddleware,
    ReloadEnvMiddleware,
    SilentRefreshMiddleware,
)
from .deprecation_mw import DeprecationHeaderMiddleware
from .error_handler import ErrorHandlerMiddleware
from .metrics_mw import MetricsMiddleware
from .middleware_core import (
    DedupMiddleware,
    HealthCheckFilterMiddleware,
    RedactHashMiddleware,
    RequestIDMiddleware,
    TraceRequestMiddleware,
)
from .rate_limit import RateLimitMiddleware
from .session_attach import SessionAttachMiddleware

logger = logging.getLogger(__name__)


def add_mw(app, mw_cls: type[BaseHTTPMiddleware], *, name: str):
    """
    Add middleware with validation - fails loudly on startup if anything is wrong.

    Args:
        app: FastAPI/Starlette app instance
        mw_cls: Middleware class to add
        name: Human-readable name for error messages

    Raises:
        RuntimeError: If middleware class is invalid
    """
    # Validate middleware class is not None
    if mw_cls is None:
        raise RuntimeError(
            f"Middleware '{name}' resolved to None - check imports in app.middleware"
        )

    # Validate it's actually a class
    if not inspect.isclass(mw_cls):
        raise RuntimeError(f"Middleware '{name}' is not a class: {mw_cls!r}")

    # Validate it subclasses BaseHTTPMiddleware
    if not issubclass(mw_cls, BaseHTTPMiddleware):
        raise RuntimeError(
            f"Middleware '{name}' must subclass BaseHTTPMiddleware (got {mw_cls})"
        )

    # Add the middleware
    app.add_middleware(mw_cls)

    # Log successful addition (for debugging)
    logger.debug(f"✅ Added middleware: {name} ({mw_cls.__name__})")


def _is_truthy(v: str | None) -> bool:
    """Check if environment variable is truthy."""
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def register_canonical_middlewares(app: FastAPI, *, csrf_enabled: bool = True, cors_origins: list[str] | None = None) -> None:
    """
    Register middlewares in canonical order with validation.

    This is the ONLY place where middleware should be registered.
    Order: outermost → innermost (first added runs first).

    Args:
        app: FastAPI app instance
        csrf_enabled: Whether to enable CSRF middleware
        cors_origins: List of allowed CORS origins
    """
    # Environment checks for conditionals
    env = (os.getenv("ENV") or "dev").strip().lower()
    dev_mode = _is_truthy(os.getenv("DEV_MODE"))
    in_ci = _is_truthy(os.getenv("CI")) or "PYTEST_CURRENT_TEST" in os.environ
    rate_limit_enabled = _is_truthy(os.getenv("RATE_LIMIT_ENABLED", "1")) and not in_ci
    legacy_error_mw = _is_truthy(os.getenv("LEGACY_ERROR_MW"))

    logger.info("Setting up canonical middleware stack with csrf_enabled=%s, cors_origins=%s", csrf_enabled, cors_origins)

    # =========================================================================
    # CANONICAL MIDDLEWARE ORDER - OUTERMOST → INNERMOST
    # =========================================================================

    # CORS layers (outermost)
    cors_origins_list = cors_origins or ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(CorsPreflightMiddleware, allow_origins=cors_origins_list)
    add_mw(app, SafariCORSCacheFixMiddleware, name="SafariCORSCacheFixMiddleware")

    # CORSMiddleware from Starlette
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Request processing chain
    add_mw(app, RequestIDMiddleware, name="RequestIDMiddleware")
    add_mw(app, TraceRequestMiddleware, name="TraceRequestMiddleware")
    add_mw(app, RedactHashMiddleware, name="RedactHashMiddleware")
    add_mw(app, HealthCheckFilterMiddleware, name="HealthCheckFilterMiddleware")

    # Rate limiting (conditional)
    if rate_limit_enabled:
        add_mw(app, RateLimitMiddleware, name="RateLimitMiddleware")

    # Session and auth
    add_mw(app, SessionAttachMiddleware, name="SessionAttachMiddleware")
    add_mw(app, SilentRefreshMiddleware, name="SilentRefreshMiddleware")
    add_mw(app, DedupMiddleware, name="DedupMiddleware")

    # Audit, metrics, and deprecation (CRITICAL ORDER: Metrics BEFORE Deprecation in execution)
    # Note: Since FastAPI stores middleware in reverse order, we add Deprecation first
    # so it appears after Metrics in user_middleware (executing after Metrics)
    add_mw(app, AuditMiddleware, name="AuditMiddleware")
    add_mw(app, DeprecationHeaderMiddleware, name="DeprecationHeaderMiddleware")  # <- Add first (appears second in user_middleware)
    add_mw(app, MetricsMiddleware, name="MetricsMiddleware")              # <- Add second (appears first in user_middleware)

    # CSRF protection (conditional)
    if csrf_enabled:
        add_mw(app, CSRFMiddleware, name="CSRFMiddleware")

    # Legacy error middlewares (conditional)
    if legacy_error_mw:
        add_mw(app, EnhancedErrorHandlingMiddleware, name="EnhancedErrorHandlingMiddleware")
        add_mw(app, ErrorHandlerMiddleware, name="ErrorHandlerMiddleware")
        logger.warning("Legacy error middlewares enabled (LEGACY_ERROR_MW=1) — not recommended.")

    # ReloadEnvMiddleware (innermost, dev/CI only)
    if dev_mode and not in_ci:
        add_mw(app, ReloadEnvMiddleware, name="ReloadEnvMiddleware")

    # =========================================================================
    # VALIDATION - GUARD AGAINST DRIFT
    # =========================================================================

    # Expected order in FastAPI's internal storage (inner→outer due to reversal)
    # Note: Due to FastAPI's reverse storage, the order here matches execution order
    EXPECTED = [
        "ReloadEnvMiddleware",            # innermost (added last)
        "ErrorHandlerMiddleware",         # conditional
        "EnhancedErrorHandlingMiddleware", # conditional
        "CSRFMiddleware",                 # conditional
        "MetricsMiddleware",              # executes BEFORE Deprecation (critical!)
        "DeprecationHeaderMiddleware",   # executes AFTER Metrics (critical!)
        "AuditMiddleware",
        "DedupMiddleware",
        "SilentRefreshMiddleware",
        "SessionAttachMiddleware",
        "RateLimitMiddleware",            # conditional
        "HealthCheckFilterMiddleware",
        "RedactHashMiddleware",
        "TraceRequestMiddleware",
        "RequestIDMiddleware",
        "CORSMiddleware",
        "SafariCORSCacheFixMiddleware",
        "CorsPreflightMiddleware",        # outermost (added first)
    ]

    # Build actual order, skipping conditionals that weren't added
    actual = [mw.cls.__name__ for mw in app.user_middleware]
    expected_filtered = []
    for name in EXPECTED:
        if name == "CSRFMiddleware" and not csrf_enabled:
            continue
        elif name == "RateLimitMiddleware" and not rate_limit_enabled:
            continue
        elif name in ["EnhancedErrorHandlingMiddleware", "ErrorHandlerMiddleware"] and not legacy_error_mw:
            continue
        elif name == "ReloadEnvMiddleware" and not (dev_mode and not in_ci):
            continue
        expected_filtered.append(name)

    # Validate order
    if actual != expected_filtered:
        msg = (
            "\n--- Middleware order mismatch ---\n"
            f"Expected: {' > '.join(expected_filtered)}\n"
            f"Actual:   {' > '.join(actual)}\n"
        )

        # Environment-aware error handling
        if env in {"dev", "ci", "test"}:
            raise RuntimeError(msg)
        else:
            logger.error(msg)  # Production: log error but continue

    # Belt-and-suspenders: forbid rogue re-registration
    _seen = set()
    for mw in app.user_middleware:
        name = mw.cls.__name__
        if name in _seen:
            raise RuntimeError(f"Duplicate middleware detected: {name}")
        _seen.add(name)

    logger.info("✅ Canonical middleware stack validated with %d middlewares", len(actual))

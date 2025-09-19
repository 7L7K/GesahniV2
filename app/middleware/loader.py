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
from .auth_diag import AuthDiagMiddleware

# Deprecated custom CORS layers removed in favor of a single CORSMiddleware
from .custom import (
    EnhancedErrorHandlingMiddleware,
    ReloadEnvMiddleware,
    SilentRefreshMiddleware,
)
from .deprecation_mw import DeprecationHeaderMiddleware
from .error_handler import ErrorHandlerMiddleware
from .legacy_headers import LegacyHeadersMiddleware
from .metrics_mw import MetricsMiddleware
from .middleware_core import (
    APILoggingMiddleware,
    DedupMiddleware,
    HealthCheckFilterMiddleware,
    RedactHashMiddleware,
    RequestIDMiddleware,
    TraceRequestMiddleware,
)
from .origin_guard import OriginGuardMiddleware
from .rate_limit import RateLimitMiddleware
from .session_attach import SessionAttachMiddleware

logger = logging.getLogger(__name__)


def add_mw(
    app,
    mw_cls: type[BaseHTTPMiddleware],
    *,
    name: str,
    **kwargs,
):
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
    app.add_middleware(mw_cls, **kwargs)

    # Log successful addition (for debugging)
    logger.debug(f"✅ Added middleware: {name} ({mw_cls.__name__})")


def _is_truthy(v: str | None) -> bool:
    """Check if environment variable is truthy."""
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def register_canonical_middlewares(
    app: FastAPI, *, csrf_enabled: bool = True, cors_origins: list[str] | None = None
) -> None:
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
    # Rate limiting is enabled by default in dev, can be disabled with RATE_LIMIT_ENABLED=0
    rate_limit_enabled = _is_truthy(os.getenv("RATE_LIMIT_ENABLED", "1")) and not in_ci
    legacy_error_mw = _is_truthy(os.getenv("LEGACY_ERROR_MW"))
    legacy_headers_enabled = _is_truthy(os.getenv("GSN_ENABLE_LEGACY_GOOGLE")) or (
        _is_truthy(os.getenv("LEGACY_MUSIC_HTTP")) and not in_ci
    )

    # Test-specific middleware disable flags
    csrf_disabled = _is_truthy(os.getenv("CSRF_DISABLE"))
    origin_guard_disabled = _is_truthy(os.getenv("ORIGIN_GUARD_DISABLE"))

    logger.info(
        "Setting up canonical middleware stack with csrf_enabled=%s, cors_origins=%s",
        csrf_enabled,
        cors_origins,
    )

    # =========================================================================
    # CANONICAL MIDDLEWARE ORDER - OUTERMOST → INNERMOST
    # =========================================================================

    # CORS: mount a single Starlette CORSMiddleware ONLY when explicit origins provided.
    # In dev proxy (same-origin), do not mount any CORS middleware.
    origin_candidates = [o for o in (cors_origins or []) if o and o.strip()]
    allow_origins = list({o.strip().rstrip("/") for o in origin_candidates})
    cors_enabled = bool(allow_origins)
    if cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
            expose_headers=["X-Request-ID", "X-Error-Code", "X-Error-ID", "X-Trace-ID"],
            max_age=3600,
        )

    # Request processing chain
    # RequestIDMiddleware must run before APILoggingMiddleware to set request ID
    add_mw(app, RequestIDMiddleware, name="RequestIDMiddleware")
    add_mw(app, APILoggingMiddleware, name="APILoggingMiddleware")
    # Dev-only diagnostic middleware: provide redacted auth/cookie summaries
    try:
        add_mw(app, AuthDiagMiddleware, name="AuthDiagMiddleware")
    except Exception:
        # Best-effort: do not fail startup if diag middleware cannot be added
        logger.debug("AuthDiagMiddleware not added (optional)")
    add_mw(app, TraceRequestMiddleware, name="TraceRequestMiddleware")
    add_mw(app, RedactHashMiddleware, name="RedactHashMiddleware")
    add_mw(app, HealthCheckFilterMiddleware, name="HealthCheckFilterMiddleware")

    # Session and auth (must run BEFORE rate limiting to provide user_id)
    # Enable session attachment for admin endpoints to work properly
    session_attach_enabled = _is_truthy(os.getenv("SESSION_ATTACH_ENABLED", "1"))
    if session_attach_enabled:
        add_mw(app, SessionAttachMiddleware, name="SessionAttachMiddleware")
    add_mw(app, SilentRefreshMiddleware, name="SilentRefreshMiddleware")

    # Rate limiting (conditional - AFTER auth so it can key by user_id)
    if rate_limit_enabled:
        add_mw(app, RateLimitMiddleware, name="RateLimitMiddleware")

    add_mw(app, DedupMiddleware, name="DedupMiddleware")

    # Audit, metrics, and deprecation (CRITICAL ORDER: Metrics BEFORE Deprecation in execution)
    # Note: Since FastAPI stores middleware in reverse order, we add Deprecation first
    # so it appears after Metrics in user_middleware (executing after Metrics)
    add_mw(app, AuditMiddleware, name="AuditMiddleware")
    add_mw(
        app, DeprecationHeaderMiddleware, name="DeprecationHeaderMiddleware"
    )  # <- Add first (appears second in user_middleware)
    add_mw(
        app, MetricsMiddleware, name="MetricsMiddleware"
    )  # <- Add second (appears first in user_middleware)

    # Legacy headers (conditional)
    if legacy_headers_enabled:
        add_mw(app, LegacyHeadersMiddleware, name="LegacyHeadersMiddleware")

    # Origin guard protection (conditional - skip if disabled for tests)
    if not origin_guard_disabled:
        add_mw(
            app,
            OriginGuardMiddleware,
            name="OriginGuardMiddleware",
            allowed_origins=allow_origins,
        )

    # CSRF protection (conditional - skip if disabled for tests)
    if csrf_enabled and not csrf_disabled:
        add_mw(app, CSRFMiddleware, name="CSRFMiddleware")

    # Legacy error middlewares (conditional)
    if legacy_error_mw:
        add_mw(
            app, EnhancedErrorHandlingMiddleware, name="EnhancedErrorHandlingMiddleware"
        )
        add_mw(app, ErrorHandlerMiddleware, name="ErrorHandlerMiddleware")
        logger.warning(
            "Legacy error middlewares enabled (LEGACY_ERROR_MW=1) — not recommended."
        )

    # ReloadEnvMiddleware (innermost, dev/CI only)
    if dev_mode and not in_ci:
        add_mw(app, ReloadEnvMiddleware, name="ReloadEnvMiddleware")

    # =========================================================================
    # VALIDATION - GUARD AGAINST DRIFT
    # =========================================================================

    # Expected order in FastAPI's internal storage (inner→outer due to reversal)
    # Note: Due to FastAPI's reverse storage, the order here matches execution order
    EXPECTED = [
        "ReloadEnvMiddleware",  # innermost (added last)
        "ErrorHandlerMiddleware",  # conditional
        "EnhancedErrorHandlingMiddleware",  # conditional
        "CSRFMiddleware",  # conditional
        "OriginGuardMiddleware",
        "MetricsMiddleware",  # executes BEFORE Deprecation (critical!)
        "DeprecationHeaderMiddleware",  # executes AFTER Metrics (critical!)
        "LegacyHeadersMiddleware",  # conditional, executes AFTER Deprecation
        "AuditMiddleware",
        "DedupMiddleware",
        "RateLimitMiddleware",  # conditional - AFTER auth, BEFORE handler
        "SilentRefreshMiddleware",
        "SessionAttachMiddleware",  # conditional - BEFORE HealthCheckFilterMiddleware
        "HealthCheckFilterMiddleware",
        "RedactHashMiddleware",
        "TraceRequestMiddleware",
        "AuthDiagMiddleware",
        "APILoggingMiddleware",
        "RequestIDMiddleware",
        "CORSMiddleware",
    ]

    # Build actual order, skipping conditionals that weren't added
    actual = [mw.cls.__name__ for mw in app.user_middleware]
    expected_filtered = []
    for name in EXPECTED:
        if name == "CSRFMiddleware" and (not csrf_enabled or csrf_disabled):
            continue
        elif name == "OriginGuardMiddleware" and origin_guard_disabled:
            continue
        elif name == "RateLimitMiddleware" and not rate_limit_enabled:
            continue
        elif (
            name in ["EnhancedErrorHandlingMiddleware", "ErrorHandlerMiddleware"]
            and not legacy_error_mw
        ):
            continue
        elif name == "ReloadEnvMiddleware" and not (dev_mode and not in_ci):
            continue
        elif name == "SessionAttachMiddleware" and not _is_truthy(
            os.getenv("SESSION_ATTACH_ENABLED", "1")
        ):
            continue
        elif name == "LegacyHeadersMiddleware" and not legacy_headers_enabled:
            continue
        if name == "CORSMiddleware" and not cors_enabled:
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

    logger.info(
        "✅ Canonical middleware stack validated with %d middlewares", len(actual)
    )

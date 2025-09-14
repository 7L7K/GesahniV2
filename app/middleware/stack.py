"""
FastAPI Middleware Stack - Single Source of Truth

This module contains the canonical middleware stack configuration for the GesahniV2 application.

⚠️  IMPORTANT: This is the ONLY place where middleware order should be modified!
   Do not add middleware elsewhere in the codebase.

See the header comment below for detailed documentation on environment controls and usage.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.csrf import CSRFMiddleware

# Local middlewares (all must be import-safe)
from app.middleware import (
    DedupMiddleware,
    HealthCheckFilterMiddleware,
    RateLimitMiddleware,
    RedactHashMiddleware,
    ReloadEnvMiddleware,
    RequestIDMiddleware,
    SessionAttachMiddleware,
    SilentRefreshMiddleware,
    TraceRequestMiddleware,
    add_mw,
)
from app.middleware.audit_mw import AuditMiddleware

# Deprecated custom CORS layers removed; use a single Starlette CORSMiddleware only when needed
from app.middleware.custom import EnhancedErrorHandlingMiddleware
from app.middleware.deprecation_mw import DeprecationHeaderMiddleware
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.metrics_mw import MetricsMiddleware

log = logging.getLogger(__name__)

# =============================================================================
# MIDDLEWARE STACK - SINGLE SOURCE OF TRUTH
# =============================================================================
#
# ⚠️  CRITICAL: This file is the ONLY place to modify middleware order! ⚠️
#
# - Add order = outer → inner (first added runs outermost)
# - To change middleware order, edit the EXPECTED list and setup logic below
# - Do NOT add middleware elsewhere in the codebase
#
# Environment toggles used:
# - CSRF_ENABLED=1|0 (default: 1) - Enable/disable CSRF middleware
# - CORS_ORIGINS="origin1,origin2" - Comma-separated allowed CORS origins
# - RATE_LIMIT_ENABLED=1|0 (default: 1) - Enable/disable rate limiting (auto-disabled in CI)
# - LEGACY_ERROR_MW=1 - Enable legacy error handling middlewares (not recommended)
# - CI/dev detection: RATE_LIMIT_ENABLED auto-disabled in CI, ReloadEnvMiddleware only in dev
#
# To verify: Run `python scripts/print_middleware.py`
# =============================================================================


def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def setup_middleware_stack(
    app: FastAPI, *, csrf_enabled: bool = True, cors_origins: list[str] | None = None
) -> None:
    """
    SINGLE SOURCE OF TRUTH for FastAPI middleware stack configuration.

    ⚠️  DO NOT modify middleware order elsewhere in the codebase!

    Add order = outer → inner:
    - First middleware added runs outermost (closest to client)
    - Last middleware added runs innermost (closest to routes)

    Environment controls:
    - csrf_enabled: Controlled by CSRF_ENABLED env var (default: True)
    - cors_origins: Controlled by CORS_ORIGINS env var (comma-separated)
    - RATE_LIMIT_ENABLED: Auto-disabled in CI environments
    - LEGACY_ERROR_MW: Enables legacy error middlewares (not recommended)

    To verify middleware order: Run `python scripts/print_middleware.py`
    """
    # NOTE: FastAPI stores app.user_middleware in reverse order (inner→outer)
    # So EXPECTED must match the actual storage order, not the addition order
    EXPECTED = [
        "ReloadEnvMiddleware",  # innermost (added last)
        "ErrorHandlerMiddleware",  # conditional
        "EnhancedErrorHandlingMiddleware",  # conditional
        "CSRFMiddleware",  # conditional
        "DeprecationHeaderMiddleware",  # runs before MetricsMiddleware in execution
        "MetricsMiddleware",  # runs after DeprecationHeaderMiddleware in execution
        "AuditMiddleware",
        "DedupMiddleware",
        "SilentRefreshMiddleware",
        "SessionAttachMiddleware",  # conditional
        "RateLimitMiddleware",  # conditional
        "HealthCheckFilterMiddleware",
        "RedactHashMiddleware",
        "TraceRequestMiddleware",
        "RequestIDMiddleware",
        "CORSMiddleware",  # if enabled
    ]

    # Environment checks for conditionals
    (os.getenv("ENV") or "dev").strip().lower()
    dev_mode = _is_truthy(os.getenv("DEV_MODE"))
    in_ci = _is_truthy(os.getenv("CI")) or "PYTEST_CURRENT_TEST" in os.environ
    rate_limit_enabled_env = os.getenv("RATE_LIMIT_ENABLED", "1")
    rate_limit_enabled = _is_truthy(rate_limit_enabled_env) and not in_ci
    legacy_error_mw = _is_truthy(os.getenv("LEGACY_ERROR_MW"))

    log.info(
        "Setting up middleware stack with csrf_enabled=%s, cors_origins=%s",
        csrf_enabled,
        cors_origins,
    )

    # Add middleware in exact order (outer → inner)

    # CORS: only mount when explicit origins provided (cross-origin prod).
    cors_enabled = bool(cors_origins and [o for o in cors_origins if o])
    if cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(
                {o.strip().rstrip("/") for o in cors_origins or [] if o and o.strip()}
            ),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
            expose_headers=["X-Request-ID", "X-Error-Code", "X-Error-ID", "X-Trace-ID"],
            max_age=3600,
        )

    # Request ID and tracing
    add_mw(app, RequestIDMiddleware, name="RequestIDMiddleware")
    add_mw(app, TraceRequestMiddleware, name="TraceRequestMiddleware")

    # Hygiene filters
    add_mw(app, RedactHashMiddleware, name="RedactHashMiddleware")
    add_mw(app, HealthCheckFilterMiddleware, name="HealthCheckFilterMiddleware")

    # Rate limiting (conditional)
    if rate_limit_enabled:
        add_mw(app, RateLimitMiddleware, name="RateLimitMiddleware")

    # Session and auth
    session_attach_enabled = _is_truthy(os.getenv("SESSION_ATTACH_ENABLED", "1"))
    if session_attach_enabled:
        add_mw(app, SessionAttachMiddleware, name="SessionAttachMiddleware")
    add_mw(app, SilentRefreshMiddleware, name="SilentRefreshMiddleware")

    # De-duplication
    add_mw(app, DedupMiddleware, name="DedupMiddleware")

    # Audit and metrics
    add_mw(app, AuditMiddleware, name="AuditMiddleware")
    add_mw(app, MetricsMiddleware, name="MetricsMiddleware")
    # Ensure deprecated alias paths emit Deprecation header even when served by canonical handlers
    add_mw(app, DeprecationHeaderMiddleware, name="DeprecationHeaderMiddleware")

    # CSRF (conditional)
    if csrf_enabled:
        add_mw(app, CSRFMiddleware, name="CSRFMiddleware")

    # Legacy error middlewares (conditional)
    if legacy_error_mw:
        add_mw(
            app, EnhancedErrorHandlingMiddleware, name="EnhancedErrorHandlingMiddleware"
        )
        add_mw(app, ErrorHandlerMiddleware, name="ErrorHandlerMiddleware")
        log.warning(
            "Legacy error middlewares enabled (LEGACY_ERROR_MW=1) — not recommended."
        )

    # ReloadEnvMiddleware (dev/CI only, innermost)
    if dev_mode and not in_ci:
        add_mw(app, ReloadEnvMiddleware, name="ReloadEnvMiddleware")

    # Validate order
    names = [m.cls.__name__ for m in app.user_middleware]
    expected = []
    for name in EXPECTED:
        if name == "CSRFMiddleware" and not csrf_enabled:
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
            os.getenv("SESSION_ATTACH_ENABLED", "0")
        ):
            continue
        if name == "CORSMiddleware" and not cors_enabled:
            continue
        expected.append(name)

    if names != expected:
        raise RuntimeError(
            f"Middleware order mismatch.\nExpected (outer→inner): {expected}\nActual   (outer→inner): {names}"
        )

    log.info("Middleware stack setup complete with %d middlewares", len(names))


# =============================================================================
# END OF SINGLE SOURCE OF TRUTH - DO NOT MODIFY MIDDLEWARE ORDER ELSEWHERE
# =============================================================================
#
# If you need to change middleware order, modify the EXPECTED list and setup logic above.
# Do NOT add middleware in other files - this will break the canonical order!
#
# Verify changes: Run `python scripts/print_middleware.py`
# =============================================================================

# Middleware stack assembly - isolated from router modules.
# This module handles all middleware setup without importing any
# router modules that could create circular dependencies.

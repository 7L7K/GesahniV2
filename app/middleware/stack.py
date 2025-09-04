from __future__ import annotations
import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.settings_cors import (
    get_cors_origins,
    get_cors_allow_credentials,
    get_cors_allow_methods,
    get_cors_allow_headers,
    get_cors_expose_headers,
    get_cors_max_age,
)

# Local middlewares (all must be import-safe)
from app.middleware import (
    RequestIDMiddleware,
    TraceRequestMiddleware,
    ReloadEnvMiddleware,
    RedactHashMiddleware,
    HealthCheckFilterMiddleware,
    RateLimitMiddleware,
    SessionAttachMiddleware,
    SilentRefreshMiddleware,
    DedupMiddleware,
    add_mw,
)
from app.middleware.audit_mw import AuditMiddleware
from app.middleware.metrics_mw import MetricsMiddleware

log = logging.getLogger(__name__)

def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}

def setup_middleware_stack(app: FastAPI) -> None:
    """
    Deterministic stack with env-aware toggles.
    Ordering is outside-in (added first runs outermost).
    """
    env = (os.getenv("ENV") or "dev").strip().lower()
    dev_mode = _is_truthy(os.getenv("DEV_MODE"))
    in_ci = _is_truthy(os.getenv("CI")) or "PYTEST_CURRENT_TEST" in os.environ
    # Explicit feature flag for rate limiting; default on unless CI or disabled
    rate_limit_enabled_env = os.getenv("RATE_LIMIT_ENABLED", "1")
    rate_limit_enabled = _is_truthy(rate_limit_enabled_env) and not in_ci

    log.info("mw.flags env=%s dev_mode=%s in_ci=%s rate_limit_enabled_env=%s -> rate_limit_enabled=%s",
             env, dev_mode, in_ci, rate_limit_enabled_env, rate_limit_enabled)

    # 0) CORS — preflight should bypass everything else
    try:
        origins = get_cors_origins()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=get_cors_allow_credentials(),
            allow_methods=get_cors_allow_methods(),
            allow_headers=get_cors_allow_headers(),
            expose_headers=get_cors_expose_headers(),
            max_age=get_cors_max_age(),
        )
        log.debug("CORS middleware configured (origins=%s)", origins)
    except Exception as e:
        log.warning("CORS config failed: %s", e)

    # 1) Request ID + tracing come first for observability
    add_mw(app, RequestIDMiddleware)
    add_mw(app, TraceRequestMiddleware)

    # 2) Dev-only hot reload of env (cheap & safe)
    if dev_mode and not in_ci:
        add_mw(app, ReloadEnvMiddleware)

    # 3) Hygiene filters (never block requests)
    add_mw(app, RedactHashMiddleware)
    add_mw(app, HealthCheckFilterMiddleware)

    # 4) Throttles and auth/session surface (these may block)
    if rate_limit_enabled:
        add_mw(app, RateLimitMiddleware)
    else:
        log.debug("RateLimitMiddleware skipped (rate_limit_enabled=%s)", rate_limit_enabled)
    add_mw(app, SessionAttachMiddleware)
    add_mw(app, SilentRefreshMiddleware)

    # 5) De-duplication (idempotency layer)
    add_mw(app, DedupMiddleware)

    # 6) Audit & metrics (must see the final status code)
    add_mw(app, AuditMiddleware)
    add_mw(app, MetricsMiddleware)

    # 7) Legacy error middlewares — **DISABLED BY DEFAULT**
    # Your exception handlers now own the error contract.
    # Turn these back on only for temporary compatibility:
    #   LEGACY_ERROR_MW=1
    if _is_truthy(os.getenv("LEGACY_ERROR_MW")):
        try:
            from app.middleware import EnhancedErrorHandlingMiddleware, ErrorHandlerMiddleware
            add_mw(app, EnhancedErrorHandlingMiddleware)
            add_mw(app, ErrorHandlerMiddleware)
            log.warning("Legacy error middlewares enabled (LEGACY_ERROR_MW=1) — not recommended.")
        except Exception as e:
            log.warning("Legacy error middlewares not available: %s", e)

    # Safety: if CI=true but some other code added RateLimitMiddleware earlier,
    # prune it now to guarantee CI runs without rate limiting.
    if in_ci:
        original = list(getattr(app, "user_middleware", []))
        pruned = [mw for mw in original if mw.cls.__name__ != "RateLimitMiddleware"]
        if len(pruned) != len(original):
            log.warning("Pruned RateLimitMiddleware in CI mode (found %d -> kept %d)",
                        len(original), len(pruned))
            app.user_middleware = pruned  # starlette will rebuild stack on next request

def validate_middleware_order(app: FastAPI) -> None:
    """
    Assert the stack respects invariants (developer guardrails).
    """
    names = [mw.cls.__name__ for mw in getattr(app, "user_middleware", [])]
    def _must_appear(name: str):
        assert name in names, f"Expected middleware {name} to be registered"

    # Presence checks (core)
    for n in (
        "RequestIDMiddleware",
        "TraceRequestMiddleware",
        "RedactHashMiddleware",
        "HealthCheckFilterMiddleware",
        "SessionAttachMiddleware",
        "SilentRefreshMiddleware",
        "DedupMiddleware",
        "AuditMiddleware",
        "MetricsMiddleware",
    ):
        _must_appear(n)

    # Order checks (basic)
    assert names.index("RequestIDMiddleware") < names.index("TraceRequestMiddleware")
    if "RateLimitMiddleware" in names:
        assert names.index("RateLimitMiddleware") < names.index("SessionAttachMiddleware")

    # CORS should be outermost or near-outermost (added by FastAPI/Starlette as class)
    # We can't index it easily, but we can sanity-check preflight separately in smoke tests.

    
    # Why this works
    # CORS sits on the outside → OPTIONS never collides with auth/CSRF/rate limit.
    # RequestID/Trace first → every log/metric gets an ID.
    # Legacy error middlewares off → your Phase 2 handlers own the error path.
    # No imports from app.main → no cycles.

"""Middleware stack assembly - isolated from router modules.

This module handles all middleware setup without importing any
router modules that could create circular dependencies.
"""
import logging
import os
from typing import Any, List


def setup_cors_middleware(app: Any) -> None:
    """Set up CORS middleware for the application.

    Args:
        app: FastAPI application instance
    """
    # Import CORS configuration (should be lightweight)
    try:
        from ..settings_cors import (
            get_cors_origins,
            get_cors_allow_credentials,
            get_cors_allow_methods,
            get_cors_allow_headers,
            get_cors_expose_headers,
            get_cors_max_age,
            validate_cors_origins,
        )

        origins = get_cors_origins()
        allow_credentials = get_cors_allow_credentials()
        allow_methods = get_cors_allow_methods()
        allow_headers = get_cors_allow_headers()
        expose_headers = get_cors_expose_headers()
        max_age = get_cors_max_age()

        # Validate CORS origins
        validate_cors_origins(origins)

        # Store as single source of truth for HTTP+WS origin validation
        app.state.allowed_origins = origins

        # Log CORS configuration
        logging.info(
            "CORS resolved origins=%s | allow_credentials=%s | allow_methods=%s | allow_headers=%s | expose_headers=%s",
            origins,
            allow_credentials,
            allow_methods,
            allow_headers,
            expose_headers,
        )

        from starlette.middleware.cors import CORSMiddleware

        # Add standard CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=allow_credentials,
            allow_methods=allow_methods,
            allow_headers=allow_headers,
            expose_headers=expose_headers,
            max_age=max_age,
        )

    except Exception as e:
        logging.warning("Failed to set up CORS middleware: %s", e)


def setup_core_middlewares(app: Any) -> None:
    """Set up core middlewares for the application.

    Args:
        app: FastAPI application instance
    """
    try:
        # CI detection and rate limiting control
        in_ci = _is_truthy(os.getenv("CI")) or "PYTEST_CURRENT_TEST" in os.environ
        rate_limit_enabled_env = os.getenv("RATE_LIMIT_ENABLED", "1")
        rate_limit_enabled = _is_truthy(rate_limit_enabled_env) and not in_ci

        log.info("setup_core_middlewares: CI detection: in_ci=%s, rate_limit_enabled=%s", in_ci, rate_limit_enabled)

        # Import middleware components
        from ..middleware import (
            RequestIDMiddleware,
            DedupMiddleware,
            HealthCheckFilterMiddleware,
            TraceRequestMiddleware,
            AuditMiddleware,
            RedactHashMiddleware,
            MetricsMiddleware,
            RateLimitMiddleware,
            SessionAttachMiddleware,
            CSRFMiddleware,
            EnhancedErrorHandlingMiddleware,
            ErrorHandlerMiddleware,
        )

        # Core middlewares (inner → outer)
        middlewares = [
            (RequestIDMiddleware, {}),
            (DedupMiddleware, {}),
            (HealthCheckFilterMiddleware, {}),
            (TraceRequestMiddleware, {}),
            (AuditMiddleware, {}),
            (RedactHashMiddleware, {}),
            (MetricsMiddleware, {}),
        ]

        # Conditionally add RateLimitMiddleware
        if rate_limit_enabled:
            middlewares.append((RateLimitMiddleware, {}))
            log.debug("RateLimitMiddleware added to core middlewares")
        else:
            log.info("RateLimitMiddleware skipped (CI mode or disabled)")

        middlewares.append((SessionAttachMiddleware, {}))

        # Add core middlewares
        for middleware_class, kwargs in middlewares:
            app.add_middleware(middleware_class, **kwargs)

        # Add CSRF middleware (after core middlewares)
        app.add_middleware(CSRFMiddleware)

        # Error handling middlewares (outermost for error catching)
        app.add_middleware(ErrorHandlerMiddleware)
        app.add_middleware(EnhancedErrorHandlingMiddleware)

        logging.debug("Core middlewares registered successfully")

    except Exception as e:
        logging.warning("Failed to set up core middlewares: %s", e)


def setup_optional_middlewares(app: Any) -> None:
    """Set up optional middlewares for the application.

    Args:
        app: FastAPI application instance
    """
    try:
        # Dev-only middleware
        if os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}:
            try:
                from ..middleware import ReloadEnvMiddleware
                app.add_middleware(ReloadEnvMiddleware)
                logging.debug("ReloadEnvMiddleware added for dev mode")
            except ImportError:
                pass

        # Optional silent refresh middleware
        if os.getenv("SILENT_REFRESH_ENABLED", "1").lower() in {"1", "true", "yes", "on"}:
            try:
                from ..middleware import SilentRefreshMiddleware
                app.add_middleware(SilentRefreshMiddleware)
                logging.debug("SilentRefreshMiddleware added")
            except ImportError:
                pass

    except Exception as e:
        logging.warning("Failed to set up optional middlewares: %s", e)


def setup_browser_specific_middlewares(app: Any) -> None:
    """Set up browser-specific middlewares.

    Args:
        app: FastAPI application instance
    """
    try:
        # Safari CORS cache fix
        try:
            from ..middleware import SafariCORSCacheFixMiddleware
            app.add_middleware(SafariCORSCacheFixMiddleware)
            logging.debug("SafariCORSCacheFixMiddleware added")
        except ImportError:
            pass

        # CORS preflight middleware (must be outermost)
        try:
            from ..middleware.cors import CorsPreflightMiddleware

            # Get origins for preflight middleware
            try:
                from ..settings_cors import get_cors_origins
                origins = get_cors_origins()
            except ImportError:
                origins = ["*"]  # Fallback

            app.add_middleware(CorsPreflightMiddleware, allow_origins=origins)
            logging.debug("CorsPreflightMiddleware added")
        except ImportError:
            pass

    except Exception as e:
        logging.warning("Failed to set up browser-specific middlewares: %s", e)


def setup_middleware_stack(app: Any) -> None:
    """Set up the complete middleware stack for the application.

    This function should be called from create_app() to set up
    all middlewares without triggering router imports.

    Args:
        app: FastAPI application instance
    """
    logging.info("🔧 Setting up middleware stack...")

    # Set up CORS first (affects other middleware)
    setup_cors_middleware(app)

    # Set up core middlewares
    setup_core_middlewares(app)

    # Set up optional middlewares
    setup_optional_middlewares(app)

    # Set up browser-specific middlewares
    setup_browser_specific_middlewares(app)

    # Mark middleware as registered
    try:
        app.state.mw_registered = True
        logging.info("=== MIDDLEWARE STACK COMPLETE ===")
    except Exception:
        logging.debug("Failed to set middleware registered flag")


def validate_middleware_order(app: Any) -> None:
    """Validate middleware order in development.

    Args:
        app: FastAPI application instance
    """
    if os.getenv("ENV", "dev").lower() != "dev":
        return  # only validate in dev environment

    try:
        # Get current middleware names
        got = []
        for m in getattr(app, "user_middleware", []):
            if hasattr(m.cls, '__name__'):
                got.append(m.cls.__name__)
            else:
                got.append(type(m.cls).__name__)

        # Expected order (outer → inner as reported by Starlette)
        expected_outer_to_inner = [
            "CorsPreflightMiddleware",
            "SafariCORSCacheFixMiddleware",
            "CORSMiddleware",
            "CSRFMiddleware",
            "EnhancedErrorHandlingMiddleware",
            "ErrorHandlerMiddleware",
        ]

        # Add optional middlewares
        if os.getenv("SILENT_REFRESH_ENABLED", "1").lower() in {"1", "true", "yes", "on"}:
            expected_outer_to_inner.append("SilentRefreshMiddleware")

        if os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}:
            expected_outer_to_inner.append("ReloadEnvMiddleware")

        # Add core middlewares
        expected_outer_to_inner.extend([
            "SessionAttachMiddleware",
            "RateLimitMiddleware",
            "MetricsMiddleware",
            "RedactHashMiddleware",
            "AuditMiddleware",
            "TraceRequestMiddleware",
            "HealthCheckFilterMiddleware",
            "DedupMiddleware",
            "RequestIDMiddleware",  # innermost
        ])

        if got != expected_outer_to_inner:
            logging.warning(
                "Middleware order mismatch.\\n"
                f"Expected (outer→inner): {expected_outer_to_inner}\\n"
                f"Actual   (outer→inner): {got}"
            )

    except Exception as e:
        logging.debug("Middleware order validation failed: %s", e)

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
            (RateLimitMiddleware, {}),
            (SessionAttachMiddleware, {}),
        ]

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

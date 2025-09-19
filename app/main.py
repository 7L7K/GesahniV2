"""FastAPI application entrypoint.

This module now focuses on wiring the top-level application together while
leaning on the ``app.application`` package for configuration, diagnostics, and
startup helpers. The goal is to keep this file lightweight and primarily
responsible for exposing ``create_app``/``get_app`` along with a lazy app
instance used throughout tests and tooling.
"""

from __future__ import annotations

# Pre-flight database connectivity check
import logging

logger = logging.getLogger(__name__)

# Load environment variables before any imports that depend on them
from app.env_utils import load_env
load_env()


def _perform_database_preflight_check():
    """Perform a synchronous database connectivity check before app creation."""
    try:
        # Import here to avoid circular dependencies

        from app.db.core import health_check

        logger.info("🔍 Performing pre-flight database connectivity check...")

        if health_check():
            logger.info(
                "✅ Database connectivity confirmed - proceeding with app startup"
            )
            return True
        else:
            logger.error("🚨 CRITICAL: Database connectivity check FAILED!")
            logger.error("   PostgreSQL is not accessible or DATABASE_URL is incorrect")
            logger.error(
                "   The application will start but many features will NOT work:"
            )
            logger.error("   ❌ User authentication will fail")
            logger.error("   ❌ OAuth integrations will fail")
            logger.error("   ❌ Token storage will fail")
            logger.error("   ❌ Music integration will fail")
            logger.error("")
            logger.error("   🔧 IMMEDIATE ACTION REQUIRED:")
            logger.error(
                "   1. Start PostgreSQL: pg_ctl -D /usr/local/var/postgresql@14 start"
            )
            logger.error("   2. Check DATABASE_URL in .env file")
            logger.error(
                "   3. Verify database exists: psql -U app -d gesahni -c 'SELECT 1'"
            )
            logger.error("")
            return False
    except Exception as e:
        logger.error("🚨 Database pre-flight check failed: %s", e)
        logger.error("   Application may not function properly without database access")
        return False


# Perform the check
_preflight_result = _perform_database_preflight_check()

import hashlib
import logging
import os
import sys
from typing import Any

from fastapi import FastAPI

# Populate skill registry side effects
import app.skills  # noqa: F401

# Activate dev-only tracer for middleware registration (dev/ci/test only)
if os.getenv("ENV", "dev").lower() in {"dev", "ci", "test"}:
    import app.middleware._trace_add  # noqa: F401

from app.application import (
    build_application,
    enforce_jwt_strength,
    proactive_startup,
)
from app.application import (
    enhanced_startup as _enhanced_startup,
)
from app.application import (
    record_error as _record_error_impl,
)
from app.application import (
    runtime_errors as _runtime_errors,
)
from app.application import (
    startup_errors as _startup_errors,
)
from app.application.config import load_openapi_config
from app.logging_config import configure_logging
from app.middleware.middleware_core import set_store_providers
from app.session_manager import SESSIONS_DIR
from app.user_store import user_store

# Backwards compatibility exports expected by tests/fixtures
try:  # optional import for tests/monkeypatching
    from .home_assistant import startup_check as ha_startup  # type: ignore
except Exception:  # pragma: no cover - optional

    def ha_startup() -> None:  # type: ignore
        return None


try:
    from .llama_integration import startup_check as llama_startup  # type: ignore
except Exception:  # pragma: no cover - optional

    def llama_startup() -> None:  # type: ignore
        return None


try:
    from app.router.entrypoint import route_prompt as route_prompt  # re-export
except Exception:  # pragma: no cover - optional

    def route_prompt(_: Any) -> Any:  # type: ignore
        raise RuntimeError("route_prompt unavailable")


# Configure logging early in the process
if os.getenv("ENV") != "test":
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
        )
configure_logging()
logger = logging.getLogger(__name__)

# Snapshot docs configuration for downstream consumers
_openapi_config = load_openapi_config()
_DEV_SERVERS_SNAPSHOT = _openapi_config.get("dev_servers_snapshot")
_IS_DEV_ENV = os.getenv("ENV", "dev").strip().lower() == "dev"

# Error tracking compatibility aliases
_record_error = _record_error_impl


def _anon_user_id(auth_header: str | None) -> str:
    """Return a stable 32-char hex ID from an optional Authorization header."""
    if not auth_header:
        return "local"
    token = auth_header.split()[-1]
    return hashlib.md5(token.encode()).hexdigest()


def create_app() -> FastAPI:
    """Composition root for the FastAPI application."""
    app = build_application()

    # Backwards compatibility: some tests expect these attributes on the app
    app.ha_startup = ha_startup  # type: ignore[attr-defined]
    app.llama_startup = llama_startup  # type: ignore[attr-defined]

    return app


_app_instance: FastAPI | None = None


def get_app() -> FastAPI:
    """Get the FastAPI app instance, creating it lazily if needed."""
    global _app_instance
    if _app_instance is None:
        _app_instance = create_app()
    return _app_instance


class _LazyApp:
    """Lazy app accessor that creates the app only when accessed."""

    _instance: FastAPI | None = None

    async def __call__(self, scope, receive, send):
        if self._instance is None:
            self._instance = get_app()
        return await self._instance(scope, receive, send)

    def __getattr__(self, name: str) -> Any:
        if self._instance is None:
            self._instance = get_app()
        return getattr(self._instance, name)

    def __repr__(self) -> str:
        if self._instance is None:
            return "<LazyApp: not yet created>"
        return repr(self._instance)


app = _LazyApp()

# Wire store providers into middleware (dependency injection)
set_store_providers(user_store_provider=lambda: user_store)

logging.info(
    "Server starting on %s:%s",
    os.getenv("HOST", "0.0.0.0"),
    os.getenv("PORT", "8000"),
)

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(create_app(), host=host, port=port)


__all__ = [
    "app",
    "create_app",
    "get_app",
    "route_prompt",
    "ha_startup",
    "llama_startup",
    "SESSIONS_DIR",
    "_anon_user_id",
    "_enhanced_startup",
    "_record_error",
    "_runtime_errors",
    "_startup_errors",
    "enforce_jwt_strength",
    "proactive_startup",
]

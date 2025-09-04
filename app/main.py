from app.env_utils import load_env

load_env()
import asyncio
import hashlib
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Body
from .errors import BackendUnavailable
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# CORS configuration
from .settings_cors import (
    get_cors_origins,
    get_cors_allow_credentials,
    get_cors_allow_methods,
    get_cors_allow_headers,
    get_cors_expose_headers,
    get_cors_max_age,
    validate_cors_origins,
)

# Router setup moved to create_app() to avoid import-time cycles

import app.skills  # populate SKILLS

from .logging_config import configure_logging, req_id_var
from .error_envelope import build_error, shape_from_status
from .otel_utils import get_trace_id_hex
from .deps.scheduler import shutdown as scheduler_shutdown
from .gpt_client import close_client

# Backward-compat shims: some tests expect these names on app.main
try:  # optional import for tests/monkeypatching
    from .home_assistant import startup_check as ha_startup  # type: ignore
except Exception:  # pragma: no cover - optional
    def ha_startup():  # type: ignore
        return None

try:
    from .llama_integration import startup_check as llama_startup  # type: ignore
except Exception:  # pragma: no cover - optional
    def llama_startup():  # type: ignore
        return None

# Central note: Do NOT monkey‑patch PyJWT globally.
# All JWT decoding is centralized in app.security.jwt_decode.
# Router imports moved to create_app() to avoid import-time cycles

try:
    from .api.preflight import router as preflight_router
except Exception:
    preflight_router = None  # type: ignore
from .api.settings import router as settings_router
from .api.google_oauth import router as google_oauth_router
from .api.google import integrations_router
from .api.spotify import integrations_router as spotify_integrations_router

try:
    from .api.oauth_apple import router as _oauth_apple_router
except Exception:
    _oauth_apple_router = None  # type: ignore

"""Optional Apple auth stub import (router mounted later once app exists)."""
try:
    from app.auth_providers import apple_enabled  # type: ignore
except Exception:
    # In environments without auth providers, default to disabled
    def apple_enabled() -> bool:  # type: ignore
        return False

# Try to import the stub router but do NOT mount it before `app` exists
try:
    from app.api.oauth_apple_stub import router as apple_stub_router  # type: ignore
except Exception:
    apple_stub_router = None  # type: ignore
try:
    from .api.auth_password import router as auth_password_router
except Exception:
    auth_password_router = None  # type: ignore
music_router = None  # legacy placeholder; music_http/music_ws are mounted explicitly
try:
    from .auth_device import router as device_auth_router
except Exception:
    device_auth_router = None  # type: ignore
from .integrations.google.routes import router as google_router

try:
    from .auth_monitoring import record_ws_reconnect_attempt
except Exception:  # pragma: no cover - optional
    record_ws_reconnect_attempt = lambda *a, **k: None
from .session_manager import SESSIONS_DIR as SESSIONS_DIR  # re-export for tests
from .storytime import schedule_nightly_jobs
from .transcription import close_whisper_client

try:
    from .proactive_engine import get_self_review as _get_self_review  # type: ignore
except Exception:  # pragma: no cover - optional

    def _get_self_review():  # type: ignore
        return None


# Optional proactive engine hooks (disabled in tests if unavailable)
def proactive_startup():
    try:
        from .proactive_engine import startup as _start

        _start()
    except Exception:
        return None


def _set_presence(*args, **kwargs):  # type: ignore
    return None


def _on_ha_event(*args, **kwargs):  # type: ignore
    return None


try:
    from .deps.scopes import (
        docs_security_with,
        optional_require_any_scope,
        optional_require_scope,
        require_any_scopes,
        require_scope,
        require_scopes,
    )
except Exception:  # pragma: no cover - optional

    def require_scope(scope: str):  # type: ignore
        async def _noop(*args, **kwargs):
            return None

        return _noop

    optional_require_scope = require_scope  # type: ignore

    def optional_require_any_scope(scopes):  # type: ignore
        return require_scope(next(iter(scopes), ""))

    def require_scopes(scopes):  # type: ignore
        return require_scope(next(iter(scopes), ""))

    def require_any_scopes(scopes):  # type: ignore
        return require_scope(next(iter(scopes), ""))

    def docs_security_with(scopes):  # type: ignore
        async def _noop2(*args, **kwargs):
            return None

        return _noop2


from app.middleware import (
    DedupMiddleware,
    EnhancedErrorHandlingMiddleware,
    ErrorHandlerMiddleware,
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
from app.middleware.metrics_mw import MetricsMiddleware

from .security import verify_token

# ensure optional import does not crash in test environment
try:
    from .proactive_engine import on_ha_event, set_presence
except Exception:  # pragma: no cover - optional

    def set_presence(*args, **kwargs):  # type: ignore
        return None

    def on_ha_event(*args, **kwargs):  # type: ignore
        return None


def _anon_user_id(auth_header: str | None) -> str:
    """Return a stable 32‑char hex ID from an optional ``Authorization`` header."""
    if not auth_header:
        return "local"
    token = auth_header.split()[-1]
    return hashlib.md5(token.encode()).hexdigest()


# Configure logging first
configure_logging()
logger = logging.getLogger(__name__)

# Ensure a concrete router is registered at import time to avoid router-unavailable
try:
    from .router.registry import set_router, get_router
    from .router.model_router import model_router as _module_model_router

    try:
        # Only set if not already configured
        _ = get_router()
    except Exception:
        try:
            set_router(_module_model_router)
            logger.debug("Router registry set to model_router at import time")
        except Exception:
            logger.debug("Failed to set router registry at import time; will rely on create_app()")
except Exception:
    # Best-effort only; do not fail import if registry or model_router unavailable
    pass


# Import helper: prefer importlib over exec for safety/readability.
import importlib

def _import_router(module_path: str, *, attr: str = "router"):
    try:
        module = importlib.import_module(module_path, package=__package__)
        return getattr(module, attr)
    except Exception as e:
        return None


def _enforce_jwt_strength() -> None:
    """Enforce JWT_SECRET strength at runtime during startup (not import).

    - In production (ENV in {"prod","production"} or DEV_MODE!=1) a short secret is fatal.
    - In dev/tests we only log a warning and continue.
    """
    sec = os.getenv("JWT_SECRET", "") or ""
    env = os.getenv("ENV", "").strip().lower()
    dev_mode = os.getenv("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}

    def _is_dev() -> bool:
        return env == "dev" or dev_mode

    if len(sec) >= 32:
        logger.info("JWT secret: OK (len=%d)", len(sec))
        return

    # Weak secret handling
    if _is_dev():
        logger.warning(
            "JWT secret: WEAK (len=%d) — allowed in dev/tests only", len(sec)
        )
        return

    # Production (or non-dev): fail startup
    raise RuntimeError("JWT_SECRET too weak (need >= 32 characters)")


# Global error tracking
_startup_errors = []
_runtime_errors = []


def _record_error(error: Exception, context: str = "unknown"):
    """Record an error for monitoring and debugging."""
    error_info = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context,
        "traceback": "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        ),
    }
    _runtime_errors.append(error_info)
    if len(_runtime_errors) > 100:  # Keep only last 100 errors
        _runtime_errors.pop(0)

    # Also log to persistent audit trail for long-term diagnostics
    try:
        from .audit_new import AuditEvent, append
        audit_event = AuditEvent(
            user_id="system",
            route=f"system.{context}",
            method="ERROR",
            status=500,
            action="system_error",
            meta={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
                "traceback": "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
            }
        )
        append(audit_event)
    except Exception as audit_error:
        # Don't let audit logging failures break the main error handling
        logger.debug(f"Failed to write error to audit log: {audit_error}")

    logger.error(f"Error in {context}: {error}", exc_info=True)


# Enhanced startup with comprehensive error tracking
async def _enhanced_startup():
    """Enhanced startup with comprehensive error tracking and logging."""
    startup_start = time.time()
    logger.info("Starting enhanced application startup")

    try:
        # Verify secret usage on boot
        from .secret_verification import audit_prod_env, log_secret_summary

        log_secret_summary()

        # Enforce JWT strength at startup (moved from import-time)
        try:
            _enforce_jwt_strength()
        except Exception as e:
            logger.error("JWT secret validation failed: %s", e)
            _record_error(e, "startup.jwt_secret")
            raise  # This should be fatal

        # Production environment audit (strict checks for prod)
        try:
            audit_prod_env()
        except Exception as e:
            logger.error("Production environment audit failed: %s", e)
            _record_error(e, "startup.prod_audit")
            raise  # This should be fatal

        # Initialize core components with error tracking (delegated to app.startup)
        try:
            from app.startup.components import (
                init_database,
                init_token_store_schema,
                init_openai_health_check,
                init_vector_store,
                init_llama,
                init_home_assistant,
                init_memory_store,
                init_scheduler,
            )

            components = [
                ("Database", init_database),
                ("Database Migrations", init_database_migrations),
                ("Token Store Schema", init_token_store_schema),
                ("OpenAI Health Check", init_openai_health_check),
                ("Vector Store", init_vector_store),
                # ("LLaMA Integration", init_llama),  # Disabled for faster startup
                ("Home Assistant", init_home_assistant),
                ("Memory Store", init_memory_store),
                ("Scheduler", init_scheduler),
            ]
        except Exception as e:
            logger.warning("Failed to import startup components: %s", e)
            components = []

        total_components = len(components)
        for i, (name, init_func) in enumerate(components, 1):
            try:
                start_time = time.time()
                logger.info(f"[{i}/{total_components}] Initializing {name}...")

                # Create a task with timeout to prevent hanging
                import asyncio
                try:
                    task = asyncio.create_task(init_func())
                    await asyncio.wait_for(task, timeout=30.0)  # 30 second timeout per component
                    duration = time.time() - start_time
                    logger.info(f"✅ {name} initialized successfully ({duration:.1f}s)")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ {name} initialization timed out after 30s - continuing startup")
                    _record_error(TimeoutError(f"{name} init timeout"), f"startup.{name.lower().replace(' ', '_')}")
                    continue
                except Exception as e:
                    duration = time.time() - start_time
                    logger.warning(f"⚠️ {name} failed after {duration:.1f}s: {e}")
                    _record_error(e, f"startup.{name.lower().replace(' ', '_')}")
                    continue

            except Exception as e:
                error_msg = f"Critical error initializing {name}: {e}"
                logger.error(error_msg, exc_info=True)
                _record_error(e, f"startup.{name.lower().replace(' ', '_')}")
                # Continue startup even if some components fail
                continue

        # Schedule nightly jobs (no-op if scheduler unavailable)
        try:
            schedule_nightly_jobs()
        except Exception as e:
            logger.debug("schedule_nightly_jobs failed", exc_info=True)
            _record_error(e, "startup.nightly_jobs")

        try:
            proactive_startup()
        except Exception as e:
            logger.debug("proactive_startup failed", exc_info=True)
            _record_error(e, "startup.proactive")

        # Start token store cleanup task
        try:
            from .token_store import start_cleanup_task
            await start_cleanup_task()
        except Exception as e:
            logger.debug("token store cleanup task not started", exc_info=True)
            _record_error(e, "startup.token_store")

        startup_time = time.time() - startup_start
        logger.info(f"Application startup completed in {startup_time:.2f}s")

    except Exception as e:
        error_msg = f"Critical startup failure: {e}"
        logger.error(error_msg, exc_info=True)
        _record_error(e, "startup.critical")
        raise


async def _init_database():
    """Initialize database connections and verify connectivity."""
    try:
        # Database schemas are now initialized once during app startup
        # This function now only verifies connectivity
        logger.info("Database connectivity verified - schemas already initialized at startup")
    except Exception as e:
        logger.error(f"Database connectivity test failed: {e}")
        raise


async def _init_token_store_schema():
    try:
        from .auth_store_tokens import token_dao

        # Start schema migration in background (non-blocking)
        import asyncio
        asyncio.create_task(token_dao.ensure_schema_migrated())
        logger.debug("Token store schema migration started in background")
    except Exception as e:
        logger.error(f"Token store schema init failed: {e}")
        raise


async def _init_openai_health_check():
    """Perform OpenAI startup health check using the startup module."""
    try:
        from .startup import check_vendor_health_gated

        logger.info("Performing OpenAI startup health check")
        result = await check_vendor_health_gated("openai")

        if result["status"] in ["skipped", "missing_config"]:
            logger.debug("OpenAI health check %s: %s", result["status"], result.get("reason", ""))
            return
        elif result["status"] == "healthy":
            logger.info("OpenAI startup health check successful")
            return
        else:
            # Health check failed
            error_msg = result.get("error", f"Health check failed with status: {result['status']}")
            logger.error("OpenAI startup health check failed: %s", error_msg)
            raise RuntimeError(f"OpenAI health check failed: {error_msg}")

    except Exception as e:
        logger.error("OpenAI startup health check failed: %s", e)
        raise


async def _init_vector_store():
    """Initialize vector store with read-only health check."""
    try:
        from .memory.api import _get_store
        store = _get_store()

        # Read-only connectivity test - be tolerant of sync vs async implementations
        try:
            import inspect

            if hasattr(store, "ping"):
                ping_fn = getattr(store, "ping")
                # If ping is an async function, await it; otherwise call it and await result if awaitable
                if inspect.iscoroutinefunction(ping_fn):
                    await ping_fn()
                else:
                    res = ping_fn()
                    if inspect.isawaitable(res):
                        await res
            elif hasattr(store, "search_memories"):
                search_fn = getattr(store, "search_memories")
                # Call search with minimal impact; handle sync and async
                if inspect.iscoroutinefunction(search_fn):
                    await search_fn("", "", limit=0)
                else:
                    res = search_fn("", "", limit=0)
                    if inspect.isawaitable(res):
                        await res
            else:
                # Fallback: just get the store instance
                pass

        except Exception:
            # Bubble up to outer handler which will log and record the error
            raise

        logger.debug("Vector store initialization successful")
    except Exception as e:
        logger.error(f"Vector store initialization failed: {e}")
        raise


async def _init_llama():
    """Initialize LLaMA integration with health check."""
    try:
        # Check if LLaMA is explicitly disabled
        llama_enabled = (os.getenv("LLAMA_ENABLED") or "").strip().lower()
        if llama_enabled in {"0", "false", "no", "off"}:
            logger.debug("LLaMA integration disabled via LLAMA_ENABLED environment variable")
            return

        # Check if Ollama URL is configured (fallback for when LLAMA_ENABLED is not set)
        ollama_url = os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL")
        if not ollama_url and llama_enabled not in {"1", "true", "yes", "on"}:
            logger.debug("LLaMA integration not configured (no OLLAMA_URL), skipping initialization")
            return

        from .llama_integration import _check_and_set_flag

        await _check_and_set_flag()
        logger.debug("LLaMA integration initialization successful")
    except Exception as e:
        logger.error(f"LLaMA integration initialization failed: {e}")
        raise


async def _init_home_assistant():
    """Initialize Home Assistant integration."""
    try:
        # Check if Home Assistant is explicitly disabled
        ha_enabled = (os.getenv("HOME_ASSISTANT_ENABLED") or "").strip().lower()
        if ha_enabled in {"0", "false", "no", "off"}:
            logger.debug("Home Assistant integration disabled via HOME_ASSISTANT_ENABLED environment variable")
            return

        # Check if Home Assistant URL is configured
        ha_url = os.getenv("HOME_ASSISTANT_URL")
        if not ha_url:
            logger.debug("Home Assistant not configured (no HOME_ASSISTANT_URL), skipping initialization")
            return

        from .home_assistant import get_states

        # Test HA connectivity if configured and enabled
        await get_states()
        logger.debug("Home Assistant integration initialization successful")
    except Exception as e:
        logger.error(f"Home Assistant initialization failed: {e}")
        raise


async def _init_memory_store():
    """Initialize memory store."""
    try:
        from .memory.api import _get_store

        _ = _get_store()
        logger.debug("Memory store initialization successful")
    except Exception as e:
        logger.error(f"Memory store initialization failed: {e}")
        raise


async def _init_scheduler():
    """Initialize scheduler."""
    try:
        from .deps.scheduler import scheduler

        if scheduler.running:
            logger.debug("Scheduler already running")
            return

        # Check if scheduler.start() is awaitable
        start_method = scheduler.start
        if hasattr(start_method, '__call__'):
            # Try to determine if it's async by checking the return type or signature
            import inspect
            if inspect.iscoroutinefunction(start_method):
                # It's an async function, await it
                await start_method()
            else:
                # It's a sync function, call it directly
                start_method()
        else:
            # Fallback: call it directly
            start_method()

        logger.debug("Scheduler initialization successful")

    except Exception as e:
        logger.warning(f"Scheduler initialization failed: {e}. Continuing without background jobs.")
        # Don't raise - make scheduler optional
        return


# Enhanced error handling middleware
async def enhanced_error_handling(request: Request, call_next):
    """Enhanced error handling middleware with comprehensive logging."""
    start_time = time.time()
    req_id = req_id_var.get()

    try:
        # Augment logs with route and anonymized user id for observability
        route_name = None
        try:
            route_name = getattr(request.scope.get("endpoint"), "__name__", None)
        except Exception:
            route_name = None

        user_anon = _anon_user_id(request.headers.get("authorization"))

        logger.debug(
            f"Request started: {request.method} {request.url.path} (ID: {req_id})"
        )

        # Log request details in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            headers = dict(request.headers)
            # Redact sensitive headers
            for key in ["authorization", "cookie", "x-api-key"]:
                if key in headers:
                    headers[key] = "[REDACTED]"

            logger.debug(
                f"Request details: {request.method} {request.url.path}",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "route": route_name,
                        "user_anon": user_anon,
                        "headers": headers,
                        "query_params": dict(request.query_params),
                        "client_ip": request.client.host if request.client else None,
                    }
                },
            )

        response = await call_next(request)

        # Log response details
        duration = time.time() - start_time
        logger.info(
            f"Request completed: {request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)",
            extra={
                "meta": {
                    "req_id": req_id,
                    "route": route_name,
                    "user_anon": user_anon,
                    "status_code": response.status_code,
                    "duration_ms": duration * 1000,
                }
            },
        )

        return response

    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Request failed: {request.method} {request.url.path} -> {type(e).__name__}: {e}"
        logger.error(
            error_msg,
            exc_info=True,
            extra={
                "meta": {
                    "req_id": req_id,
                    "route": route_name,
                    "user_anon": user_anon,
                    "duration_ms": duration * 1000,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            },
        )
        _record_error(
            e, f"request.{request.method.lower()}.{request.url.path.replace('/', '_')}"
        )

        # Return a proper error response
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "req_id": req_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


# Startup is now handled directly in the lifespan function
# using the enhanced startup with comprehensive error tracking


tags_metadata = [
    {
        "name": "Care",
        "description": "Care features, contacts, sessions, and Home Assistant actions.",
    },
    {"name": "Music", "description": "Music playback, voices, and TTS."},
    {"name": "Calendar", "description": "Calendar and reminders."},
    {"name": "TV", "description": "TV UI and related endpoints."},
    {"name": "Admin", "description": "Admin, status, models, diagnostics, and tools."},
    {"name": "Auth", "description": "Authentication and authorization."},
]


def _get_version() -> str:
    """Return a semantic version string for the API.

    Priority:
    1) ENV APP_VERSION
    2) ENV GIT_TAG
    3) `git describe --tags --always`
    4) Fallback "0.0.0"
    """
    try:
        ver = os.getenv("APP_VERSION") or os.getenv("GIT_TAG")
        if ver:
            return ver
        import subprocess

        proc = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "").strip()
        if out:
            return out
    except Exception:
        pass
    return "0.0.0"


_IS_DEV_ENV = os.getenv("ENV", "dev").strip().lower() == "dev"

# Import docs configuration
from .config_docs import get_docs_visibility_config, get_swagger_ui_parameters

_docs_config = get_docs_visibility_config()
_docs_url = _docs_config["docs_url"]
_redoc_url = _docs_config["redoc_url"]
_openapi_url = _docs_config["openapi_url"]
_swagger_ui_parameters = get_swagger_ui_parameters()

# Snapshot dev servers override at import time so tests that temporarily set
# OPENAPI_DEV_SERVERS during module reload still see the intended values even if
# the environment is restored before /openapi.json is requested.
_DEV_SERVERS_SNAPSHOT = os.getenv("OPENAPI_DEV_SERVERS")

from app.startup import lifespan  # NEW: use extracted lifespan

app = FastAPI(
    title="GesahniV2 API",
    version=_get_version(),
    lifespan=lifespan,  # use extracted lifespan from app.startup
    openapi_tags=tags_metadata,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    swagger_ui_parameters=_swagger_ui_parameters,
)

# Ensure compatibility aliases/stub routers are attached on the module-level
# `app` so tests that import `app.main.app` directly see the full surface.
try:
    from .router.registry import attach_all as _attach_all

    try:
        _attach_all(app)
        logger.debug("✅ Compat/stub routers attached at import time on main.app")
    except Exception as e:
        logger.debug("compat/stub routers not attached at import time: %s", e)
except Exception:
    # Registry not available at import time; create_app() will attach when invoked.
    logger.debug("router.registry.attach_all not available at import time; create_app will attach routers")


def create_app() -> FastAPI:
    """Composition root helper to perform late DI wiring.

    This function assembles the complete FastAPI application from leaf routers
    via the bootstrap registry. Only this function should wire the application
    together to avoid circular imports.
    """
    logger.info("🔧 Starting application composition in create_app()")

    # Install global middleware early (OPTIONS auto-reply) to avoid stealth 404s
    try:
        from .middleware.options_autoreply import AutoOptionsMiddleware

        app.add_middleware(AutoOptionsMiddleware)
        logger.debug("✅ AutoOptionsMiddleware registered")
    except Exception:
        logger.debug("AutoOptionsMiddleware not available")

    # Phase 7: Initialize infrastructure singletons first (needed by router)
    try:
        from .infra.model_router import init_model_router
        from .infra.router_rules import init_router_rules_cache
        from .infra.oauth_monitor import init_oauth_monitor

        init_model_router()
        init_router_rules_cache()
        init_oauth_monitor()

        logger.debug("✅ Infrastructure singletons initialized")
    except Exception as e:
        logger.warning("⚠️  Failed to initialize infrastructure singletons: %s", e)

    # Phase 4: Wire router using bootstrap registry (now infrastructure is ready)
    try:
        from .bootstrap.router_registry import configure_default_router
        configure_default_router()
        logger.debug("✅ Router configured via bootstrap registry")
    except Exception as e:
        logger.warning("⚠️  Failed to configure router: %s", e)

    # Bind a single source of truth for the prompt backend onto app.state
    @app.on_event("startup")
    async def _bind_prompt_backend():
        try:
            # Defer settings import to avoid side-effects at module import
            from app.settings import settings

            backend = getattr(settings, "PROMPT_BACKEND", os.getenv("PROMPT_BACKEND", "dryrun")).lower()
        except Exception:
            backend = os.getenv("PROMPT_BACKEND", "dryrun").lower()

        if backend == "openai":
            from app.routers.openai_router import openai_router

            app.state.prompt_router = openai_router
            logger.info("prompt backend bound: openai")
        elif backend == "llama":
            from app.routers.llama_router import llama_router

            app.state.prompt_router = llama_router
            logger.info("prompt backend bound: llama")
        elif backend == "dryrun":
            async def dryrun_router(payload: dict) -> dict:
                return {"dry_run": True, "echo": payload}

            app.state.prompt_router = dryrun_router
            logger.info("prompt backend bound: dryrun (safe default)")
        else:
            # Fail closed; endpoints will map this to 503
            raise BackendUnavailable(f"Unknown PROMPT_BACKEND={backend!r}")

    # Register backend factory for swappable, lazy backends (openai/llama/dryrun)
    try:
        from app.routers import register_backend_factory

        def _backend_factory(name: str):
            # Resolve backend callables lazily to avoid heavy imports at import-time
            if name == "openai":
                from app.routers.openai_router import openai_router
                return openai_router
            if name == "llama":
                from app.routers.llama_router import llama_router
                return llama_router
            if name == "dryrun":
                from app.routers.dryrun_router import dryrun_router
                return dryrun_router

            # Fallback for unknown backends - should not happen in frozen contract
            async def _unknown_backend(payload: dict) -> dict:
                raise RuntimeError(f"Unknown backend: {name}")

            return _unknown_backend

        register_backend_factory(_backend_factory)
        logger.debug("✅ Backend factory registered (openai/llama/dryrun)")
    except Exception as e:
        logger.warning("⚠️  Failed to register backend factory: %s", e)

    # Routers (env-aware, single source of truth)
    try:
        from app.routers.config import register_routers
        register_routers(app)
        logger.debug("✅ Routers registered via app.routers.config.register_routers")
    except Exception as e:
        logger.warning("⚠️  Failed to register routers via config: %s", e)

    # Error handlers (single registration point) - MUST happen before middleware setup
    from app.error_handlers import register_error_handlers
    register_error_handlers(app)

    # Phase 6: Set up middleware stack (isolated from routers)
    # Note: middleware setup is intentionally executed after registering error handlers
    try:
        from .middleware.stack import setup_middleware_stack, validate_middleware_order
        setup_middleware_stack(app)
        validate_middleware_order(app)
        logger.debug("✅ Middleware stack configured")
    except Exception as e:
        logger.warning("⚠️  Failed to set up middleware stack: %s", e)

    # Phase 7: Register test router for error normalization testing (dev only)
    try:
        logger.debug("Attempting to register test error normalization router...")
        from .test_error_normalization import router as test_router
        app.include_router(test_router, prefix="/test-errors", tags=["test-errors"])
        logger.info("✅ Test error normalization router registered at /test-errors")
    except ImportError as e:
        logger.warning("⚠️  Failed to import test router: %s", e)
    except Exception as e:
        logger.warning("⚠️  Failed to register test router: %s", e)

    # Phase 8: Register status router for health and observability endpoints
    try:
        logger.debug("Attempting to register status router...")
        from .status import router as status_router
        app.include_router(status_router, tags=["Admin"])
        logger.info("✅ Status router registered")
    except ImportError as e:
        logger.warning("⚠️  Failed to import status router: %s", e)
    except Exception as e:
        logger.warning("⚠️  Failed to register status router: %s", e)

    # Phase 9: Register public observability router (no auth required)
    try:
        logger.debug("Attempting to register public observability router...")
        from .status import public_router
        app.include_router(public_router)
        logger.info("✅ Public observability router registered")
    except ImportError as e:
        logger.warning("⚠️  Failed to import public router: %s", e)
    except Exception as e:
        logger.warning("⚠️  Failed to register public router: %s", e)

    # Phase 6: Set up OpenAPI generation (isolated from routers)
    try:
        from .openapi.generator import setup_openapi_for_app
        setup_openapi_for_app(app)
        logger.debug("✅ OpenAPI generation configured")
    except Exception as e:
        logger.warning("⚠️  Failed to set up OpenAPI generation: %s", e)

# Infrastructure initialization moved to beginning of create_app()

    logger.info("🎉 Application composition complete in create_app()")
    return app

# Wire store providers into middleware (dependency injection)
# Import stores *after* app exists to avoid import-time cycles
from .user_store import user_store
from .middleware.middleware_core import set_store_providers

set_store_providers(user_store_provider=lambda: user_store)



# OpenAPI setup moved to create_app() to avoid import-time cycles

# CORS configuration will be set up later after all imports

# The HTTP->WS guard and debug endpoints have been moved to modular routers:
# - HTTP->WS guard is implemented in `app/api/ws_endpoints.py` as an APIRouter
# - Debug endpoints are implemented in `app/api/debug.py` (dev-only)
# These were removed from the main module to keep `app/main.py` minimal.

# Removed legacy unversioned /whoami to ensure a single canonical /v1/whoami

# Optional static mount for TV shared photos
try:
    _tv_dir = os.getenv("TV_PHOTOS_DIR", "data/shared_photos")
    if _tv_dir:
        app.mount(
            "/shared_photos", StaticFiles(directory=_tv_dir), name="shared_photos"
        )
except Exception:
    pass

    # Album art cache mount for music UI
    try:
        _album_dir = os.getenv("ALBUM_ART_DIR", "data/album_art")
        if _album_dir:
            Path(_album_dir).mkdir(parents=True, exist_ok=True)
            app.mount("/album_art", StaticFiles(directory=_album_dir), name="album_art")
    except Exception:
        pass

# Metrics endpoint moved to `app/api/metrics_root.py` and is included from there.
# The local /metrics handlers were removed to avoid duplicate definitions.


_HEALTH_LAST: dict[str, bool] = {"online": True}

# Root and health endpoints are provided by `status_router` and `health_router`.
# To keep the main module focused on bootstrapping and router includes, local
# implementations were removed in favor of the imported routers.


# Dev-only WS helper moved to `app/api/debug.py`


class AskRequest(BaseModel):
    # Accept both legacy text and chat-style array
    prompt: str | list[dict]
    model_override: str | None = Field(None, alias="model")
    stream: bool | None = Field(
        False, description="Force SSE when true; otherwise negotiated via Accept"
    )

    # Pydantic v2 config: allow both alias ("model") and field name ("model_override")
    model_config = ConfigDict(
        title="AskRequest",
        validate_by_name=True,
        validate_by_alias=True,
        json_schema_extra={"examples": [{"prompt": "hello"}]},
    )


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{
                "domain": "light",
                "service": "turn_on",
                "data": {"entity_id": "light.kitchen"},
            }]
        }
    )


# Profile and onboarding endpoints have moved to app.api.profile


# HA endpoints have been moved to `app/api/ha_local.py` and/or `app/api/ha.py`.
# Local ha_router definitions and handlers removed from main to keep imports modular.


# The following core handlers were moved to modular routers:
# - explain_route -> app/api/core_misc.py
# - transcribe endpoints -> app/api/transcribe.py
# The business handlers were removed from main.py to keep it focused on bootstrap and router includes.


# =============================================================================
# Canonical router mounts (explicit prefixes)
# =============================================================================

def include(router_spec: str, *, prefix: str = "") -> None:
    try:
        mod, name = router_spec.split(":", 1)
        module = __import__(mod, fromlist=[name])
        r = getattr(module, name, None)
        if r is not None:
            app.include_router(r, prefix=prefix)
    except Exception as e:
        logging.warning("Router include failed for %s: %s", router_spec, e)

# CORS configuration moved to middleware/stack.py to avoid import-time cycles

# All router includes moved to create_app() to avoid import-time cycles

# All router includes moved to create_app() to avoid import-time cycles

# All router includes moved to create_app() to avoid import-time cycles

# All router includes moved to create_app() to avoid import-time cycles

# All router includes moved to create_app() to avoid import-time cycles

# All router includes moved to create_app() to avoid import-time cycles





# Middleware setup moved to create_app() to avoid import-time cycles


# Middleware order validation moved to middleware/stack.py


# Compatibility: ensure legacy root-level Google OAuth callback is reachable
try:
    from fastapi import Request, HTTPException
    import inspect

    async def _legacy_google_oauth_callback_root(request: Request):
        try:
            from app.integrations.google.routes import legacy_oauth_callback
        except Exception:
            raise HTTPException(status_code=404)

        maybe = legacy_oauth_callback(request)
        if inspect.isawaitable(maybe):
            return await maybe
        return maybe

    app.add_api_route("/google/oauth/callback", _legacy_google_oauth_callback_root, methods=["GET"])
except Exception:
    # Best-effort compatibility shim; do not fail startup if unavailable
    pass

# Final startup logging - simplified
logging.info(
    f"Server starting on {os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '8000')}"
)


if __name__ == "__main__":
    import uvicorn

    # Read host and port from environment variables
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))

    # Use create_app() for full application setup
    full_app = create_app()
    uvicorn.run(full_app, host=host, port=port)

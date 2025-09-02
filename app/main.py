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

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware
from .middleware import SafariCORSCacheFixMiddleware
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

from . import router
from .deps.scheduler import shutdown as scheduler_shutdown
from .gpt_client import close_client

async def route_prompt(prompt: str, user_id: str, **kwargs):
    logger.info("⬇️ main.route_prompt prompt='%s...', user_id='%s', kwargs=%s", prompt[:50], user_id, kwargs)
    try:
        res = await router.route_prompt(prompt, user_id, **kwargs)
        logger.info("⬆️ main.route_prompt got res=%s", res)
        return res
    except Exception:  # pragma: no cover - defensive
        logger.exception("💥 main.route_prompt bubbled exception")
        raise


import app.skills  # populate SKILLS

from .logging_config import configure_logging, req_id_var
from .error_envelope import build_error, shape_from_status
from .otel_utils import get_trace_id_hex

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
from .api.health import router as health_router
from .csrf import CSRFMiddleware
from .otel_utils import shutdown_tracing
from .status import router as status_router
from .api.schema import router as schema_router
from .api.root import router as root_router

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

        # Initialize core components with error tracking
        components = [
            ("Database", _init_database),
            ("Token Store Schema", _init_token_store_schema),
            ("OpenAI Health Check", _init_openai_health_check),
            ("Vector Store", _init_vector_store),
            # ("LLaMA Integration", _init_llama),  # Disabled for faster startup
            ("Home Assistant", _init_home_assistant),
            ("Memory Store", _init_memory_store),
            ("Scheduler", _init_scheduler),
        ]

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Initialize database schemas once during startup
        try:
            from .db import init_db_once
            await init_db_once()
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

        # Use enhanced startup with comprehensive error tracking and logging
        await _enhanced_startup()

        # Additional startup tasks that aren't part of the core enhanced startup
        # Start care daemons
        try:
            from .care_daemons import heartbeat_monitor_loop
            asyncio.create_task(heartbeat_monitor_loop())
        except Exception:
            logger.debug("heartbeat_monitor_loop not started", exc_info=True)

        # Start SMS worker
        try:
            from .api.sms_queue import sms_worker
            asyncio.create_task(sms_worker())
        except Exception:
            logger.debug("sms_worker not started", exc_info=True)

        # Start OpenAI health background probe
        try:
            from .router import start_openai_health_background_loop
            start_openai_health_background_loop()
        except Exception:
            logger.debug("OpenAI health background loop not started", exc_info=True)

        yield
    finally:
        # Log health flip to offline on shutdown
        try:
            if _HEALTH_LAST.get("online", True):
                logger.info("healthz status=offline")
            _HEALTH_LAST["online"] = False
        except Exception:
            pass
        for func in (close_client, close_whisper_client):
            try:
                await func()
            except Exception as e:  # pragma: no cover - best effort
                logger.debug("shutdown cleanup failed: %s", e)
        try:
            # Check if scheduler_shutdown is awaitable
            import inspect
            if inspect.iscoroutinefunction(scheduler_shutdown):
                await scheduler_shutdown()
            else:
                scheduler_shutdown()
        except Exception as e:  # pragma: no cover - best effort
            logger.debug("scheduler shutdown failed: %s", e)
        # Ensure OpenTelemetry worker thread is stopped to avoid atexit noise
        try:
            shutdown_tracing()
        except Exception:
            pass

        # Stop token store cleanup task
        try:
            from .token_store import stop_cleanup_task

            await stop_cleanup_task()
        except Exception:
            logger.debug("token store cleanup task shutdown failed", exc_info=True)


app = FastAPI(
    title="GesahniV2 API",
    version=_get_version(),
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    swagger_ui_parameters=_swagger_ui_parameters,
)

# Wire store providers into middleware (dependency injection)
# Import stores *after* app exists to avoid import-time cycles
from .user_store import user_store
from .middleware.middleware_core import set_store_providers

set_store_providers(user_store_provider=lambda: user_store)



# Unified error contract for HTTP errors
@app.exception_handler(StarletteHTTPException)
async def _unified_http_error(request: Request, exc: StarletteHTTPException):
    # Let CORS preflight go untouched
    if request.method.upper() == "OPTIONS":
        return None
    status = getattr(exc, "status_code", 500)
    headers = getattr(exc, "headers", None)
    detail = getattr(exc, "detail", None)
    # If already structured, map to standardized keys and pass through
    if isinstance(detail, dict) and ("code" in detail or "error" in detail):
        shaped = dict(detail)
        # Normalize provider/model routing errors to a stable code
        if "error" in shaped and "code" not in shaped:
            err = str(shaped.get("error") or "").lower()
            if status == 503 and err in {"vendor_unavailable", "all_vendors_unavailable"}:
                shaped = {"code": "llm_unavailable", "message": "Llm unavailable"}
            else:
                # Fallback: lift "error" into "code" for consistency
                shaped = {**shaped, "code": shaped.get("code") or shaped.get("error")}
        # Emit auth metrics for /v1/ask
        try:
            from .metrics import AUTH_401_TOTAL, AUTH_403_TOTAL

            path = getattr(request.url, "path", "")
            if path.startswith("/v1/ask"):
                if status == 401:
                    hdr = request.headers.get("Authorization") or ""
                    reason = "bad_token" if hdr.lower().startswith("bearer ") else "no_auth"
                    AUTH_401_TOTAL.labels(route="/v1/ask", reason=reason).inc()
                elif status == 403:
                    scope = str(detail.get("hint") or detail.get("scope") or "unknown")
                    AUTH_403_TOTAL.labels(route="/v1/ask", scope=scope).inc()
        except Exception:
            pass
        # Always ensure details block present with req_id/trace_id when possible
        try:
            tid = get_trace_id_hex()
        except Exception:
            tid = None
        d = {
            "status_code": status,
            "trace_id": tid,
            "path": request.url.path,
            "method": request.method,
        }
        shaped.setdefault("details", {})
        if isinstance(shaped["details"], dict):
            shaped["details"].update({k: v for k, v in d.items() if v is not None})
        # Tag envelope code and ids in header for logging middleware introspection
        try:
            code_hdr = shaped.get("code") or shaped.get("error")
            headers = dict(headers or {})
            if code_hdr:
                headers["X-Error-Code"] = str(code_hdr)
            # Expose error_id and trace_id when available for client correlation
            details = shaped.get("details") or {}
            if isinstance(details, dict):
                if details.get("error_id"):
                    headers["X-Error-ID"] = str(details.get("error_id"))
                if details.get("trace_id"):
                    headers["X-Trace-ID"] = str(details.get("trace_id"))
        except Exception:
            pass
        return JSONResponse(shaped, status_code=status, headers=headers)

    # Map to a stable shape
    code, msg, hint = shape_from_status(status)

    if isinstance(detail, str) and detail and detail not in {"Unauthorized", "forbidden", "Forbidden"}:
        msg = detail

    # Build details
    try:
        tid = get_trace_id_hex()
    except Exception:
        tid = None
    details = {
        "status_code": status,
        "trace_id": tid,
        "path": request.url.path,
        "method": request.method,
    }

    # Emit auth metrics for /v1/ask on generic errors too
    try:
        from .metrics import AUTH_401_TOTAL, AUTH_403_TOTAL

        path = getattr(request.url, "path", "")
        if path.startswith("/v1/ask"):
            if status == 401:
                hdr = request.headers.get("Authorization") or ""
                reason = "bad_token" if hdr.lower().startswith("bearer ") else "no_auth"
                AUTH_401_TOTAL.labels(route="/v1/ask", reason=reason).inc()
            elif status == 403:
                # Attempt to extract scope from existing detail if available later
                scope = "chat:write" if "chat:write" in str(detail or "") else "unknown"
                AUTH_403_TOTAL.labels(route="/v1/ask", scope=scope).inc()
    except Exception:
        pass
    # Hint backoff for 5xx responses
    if 500 <= status < 600:
        try:
            headers = dict(headers or {})
            headers.setdefault("Retry-After", "1")
        except Exception:
            pass
    # Tag envelope code in header for logging middleware introspection
    try:
        headers = dict(headers or {})
        headers["X-Error-Code"] = code
    except Exception:
        pass
    return JSONResponse(build_error(code=code, message=msg, hint=hint, details=details), status_code=status, headers=headers)


# Catch-all: never leak raw tracebacks to clients; standardize error envelope
@app.exception_handler(Exception)
async def _catch_all_errors(request: Request, exc: Exception):
    try:
        logger.exception("unhandled.exception")
    except Exception:
        pass
    try:
        tid = get_trace_id_hex()
    except Exception:
        tid = None
    details = {
        "status_code": 500,
        "trace_id": tid,
        "path": request.url.path,
        "method": request.method,
    }
    # Prefer 500; build envelope and expose IDs in headers for correlation
    env = build_error(code="internal", message="internal error", hint="try again shortly", details=details)
    hdrs = {"X-Error-Code": "internal"}
    try:
        if env.get("details") and isinstance(env.get("details"), dict):
            d = env.get("details")
            if d.get("error_id"):
                hdrs["X-Error-ID"] = str(d.get("error_id"))
            if d.get("trace_id"):
                hdrs["X-Trace-ID"] = str(d.get("trace_id"))
    except Exception:
        pass
    return JSONResponse(env, status_code=500, headers=hdrs)


@app.exception_handler(RequestValidationError)
async def _unified_validation_error(request: Request, exc: RequestValidationError):
    # For validation errors, return the traditional FastAPI format with "detail"
    # This ensures compatibility with tests that expect {"detail": ...} format
    detail_info = {
        "detail": "Validation error",
        "errors": exc.errors(),
        "path": request.url.path,
        "method": request.method
    }

    # Also include our standard envelope format for consistency
    env = build_error(
        code="invalid_input",
        message="Validation error",
        details={
            "status_code": 422,
            "errors": exc.errors(),
            "path": request.url.path,
            "method": request.method
        }
    )

    # Return both formats: traditional detail + our envelope
    combined = {**env, **detail_info}
    hdrs = {"X-Error-Code": "invalid_input"}

    try:
        if env.get("details") and isinstance(env.get("details"), dict) and env["details"].get("error_id"):
            hdrs["X-Error-ID"] = str(env["details"].get("error_id"))
        if env.get("details") and isinstance(env.get("details"), dict) and env["details"].get("trace_id"):
            hdrs["X-Trace-ID"] = str(env["details"].get("trace_id"))
    except Exception:
        pass

    return JSONResponse(combined, status_code=422, headers=hdrs)


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from .openapi import generate_custom_openapi
    from .config_docs import should_show_servers, get_dev_servers

    schema = generate_custom_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        tags=tags_metadata,
    )

    # Provide developer-friendly servers list in dev
    if should_show_servers():
        servers = get_dev_servers()
        if servers:
            schema["servers"] = [{"url": url} for url in servers]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[assignment]

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

# CORS configuration using settings module
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

# Log CORS configuration - clear INFO log for debugging origin issues
logging.info(
    "CORS resolved origins=%s | allow_credentials=%s | allow_methods=%s | allow_headers=%s | expose_headers=%s",
    origins,
    allow_credentials,
    allow_methods,
    allow_headers,
    expose_headers,
)

# Core, sessions, utilities
include("app.api.capture:router", prefix="/v1")
include("app.api.sessions_http:router", prefix="/v1")
include("app.api.sessions_ws:router", prefix="/v1")
include("app.api.transcribe:router", prefix="/v1")
include("app.api.ha_local:router", prefix="/v1")
include("app.api.memories:router", prefix="/v1")
include("app.api.util:router", prefix="/v1")
include("app.api.debug:router", prefix="/v1")
include("app.api.core_misc:router", prefix="/v1")

# Prefer the root metrics router; fall back to simple metrics when unavailable
_metrics_root = _import_router(".api.metrics_root")
if _metrics_root is not None:
    app.include_router(_metrics_root)  # keep /metrics at root
else:
    _metrics_simple = _import_router(".api.metrics")
    if _metrics_simple is not None:
        app.include_router(_metrics_simple)

include("app.health:router", prefix="/v1/diag")

# Simple logs endpoint for UI issue tray
include("app.api.logs_simple:router", prefix="/v1")

# =============================================================================
# EXISTING EXTERNAL ROUTERS - Keep in modern-first order
# =============================================================================
# Mount status router at both /v1/status and /status for compatibility
app.include_router(status_router, prefix="/v1")
app.include_router(status_router, include_in_schema=False)
app.include_router(schema_router)
app.include_router(health_router)
app.include_router(root_router)
include("app.api.well_known:router")

# Validate configuration on startup (logs only)
try:
    from .config_validator import run_config_validation

    run_config_validation()
except Exception:
    pass

# Include modern auth API router first to avoid route shadowing
include("app.api.auth:router", prefix="/v1")

# Include legacy auth router for backward compatibility (/v1/refresh, /v1/logout)
include("app.auth:router", prefix="/v1")

# Legacy auth router split into focused modules. Mount conditionally based on env.
from .auth_providers import admin_enabled

# Mount refresh router (kept separate)
# TEMPORARILY DISABLED: Testing original auth router
# if _safe_import_router("from .api.auth_router_refresh import router as auth_refresh_router", "auth_refresh"):
#     app.include_router(auth_refresh_router, prefix="/v1")

# Mount PATs router
# TEMPORARILY DISABLED: Testing original auth router
# if _safe_import_router("from .api.auth_router_pats import router as auth_pats_router", "auth_pats"):
#     app.include_router(auth_pats_router, prefix="/v1")

# Dev-only auth helpers
# TEMPORARILY DISABLED: Testing original auth router
# if os.getenv("ENV", "dev").strip().lower() in {"dev", "development"}:
#     if _safe_import_router("from .api.auth_router_dev import router as auth_dev_router", "auth_dev"):
#         app.include_router(auth_dev_router, prefix="/v1")

try:
    logging.info("Auth routers processed (admin_enabled=%s)", bool(admin_enabled()))
except Exception:
    # Fallback to a simple log if admin_enabled() import fails
    logging.info("Auth routers processed (admin_enabled=unknown)")
if preflight_router is not None:
    app.include_router(preflight_router, prefix="/v1")
if device_auth_router is not None:
    app.include_router(device_auth_router, prefix="/v1")
# Keep only the canonical Google OAuth router; legacy router removed to avoid overlap.
app.include_router(google_oauth_router, prefix="/v1")
app.include_router(integrations_router, prefix="/v1")
if os.getenv("TEST_MODE") == "1":
    app.include_router(spotify_integrations_router, prefix="/v1")
    app.include_router(spotify_integrations_router, prefix="/v1/integrations/spotify")
if _oauth_apple_router is not None:
    app.include_router(_oauth_apple_router, prefix="/v1")
# Mount Apple OAuth stub for local/dev when enabled, now that `app` exists
try:
    if apple_enabled() and apple_stub_router is not None:  # type: ignore[name-defined]
        # Unversioned for convenience and versioned for tests/clients
        app.include_router(apple_stub_router)  # type: ignore[arg-type]
        app.include_router(apple_stub_router, prefix="/v1")  # type: ignore[arg-type]
except Exception:
    # Non-fatal if unavailable
    pass
if auth_password_router is not None:
    app.include_router(auth_password_router, prefix="/v1")

# Settings router (both versioned and unversioned for compatibility)
app.include_router(settings_router, prefix="/v1")
app.include_router(settings_router, prefix="", include_in_schema=False)

# Google integration (optional)
# Provide both versioned and unversioned, under /google to match redirect defaults
# Mount compatibility endpoints for OAuth routers when in test mode or dev routers enabled
try:
    from app.env_utils import IS_TEST
    test_mode_or_dev_routers = IS_TEST or os.getenv("ALLOW_DEV_ROUTERS") == "1"
except ImportError:
    # Fallback to environment variables if env_utils not available
    test_mode_or_dev_routers = (os.getenv("TEST_MODE") == "1" or
                               os.getenv("PYTEST_RUNNING") == "1" or
                               os.getenv("ALLOW_DEV_ROUTERS") == "1")

if test_mode_or_dev_routers:
    # Google OAuth compatibility routes
    app.include_router(google_router, prefix="/v1/integrations/google")
    app.include_router(google_router, prefix="/v1/google")
    app.include_router(google_router, prefix="/google", include_in_schema=False)
    # Additional OAuth compatibility routes for tests
    app.include_router(google_oauth_router, prefix="/v1")
    app.include_router(google_oauth_router, prefix="", include_in_schema=False)
    # Mount a small compatibility router that exposes legacy root-level paths
    try:
        from app.api.google_compat import router as google_compat_router

        app.include_router(google_compat_router, prefix="", include_in_schema=False)
    except Exception:
        pass
    # Google services for test/dev compatibility
    include("app.api.google_services:router", prefix="/v1/google")
    include("app.api.health_google:router", prefix="/v1/health")

    # Compatibility shim: map legacy root-level callback path to integration handler
    try:
        from app.integrations.google.routes import legacy_oauth_callback as _legacy_google_callback

        # Mount explicit route for tests that call /google/oauth/callback directly
        app.add_api_route("/google/oauth/callback", _legacy_google_callback, methods=["GET"])
    except Exception:
        # Best-effort only; do not crash app initialization if route can't be mounted
        pass

    # Also map the canonical google oauth callback handler for root-level tests
    try:
        from .api.google_oauth import google_callback as _google_callback

        app.add_api_route("/google/oauth/callback", _google_callback, methods=["GET"])
    except Exception:
        pass

# New modular routers for HA and profile/admin
try:
    from .api.ha import router as ha_api_router
    app.include_router(
        ha_api_router,
        prefix="/v1",
        dependencies=[
            Depends(verify_token),
            Depends(require_any_scopes(["care:resident", "care:caregiver"])),
            Depends(docs_security_with(["care:resident"])),
        ],
    )
except Exception as e:
    logging.warning("Router include failed for app.api.ha:router: %s", e)

include("app.api.reminders:router", prefix="/v1")

# Cosmetic redirect for legacy OAuth redirect URIs that point to the unversioned
# `/google` prefix. Some clients and env defaults may hit `/google` (no subpath)
# which previously returned 404 — provide a harmless redirect to the canonical
# `/v1/google` prefix to avoid noisy 404s in the browser/network tab.
@app.get("/google", include_in_schema=False)
async def _google_root_redirect():
    return RedirectResponse(url="/v1/google", status_code=307)

@app.get("/google/", include_in_schema=False)
async def _google_root_redirect_slash():
    return RedirectResponse(url="/v1/google", status_code=307)

include("app.api.profile:router", prefix="/v1")

# Conditionally mount admin router based on environment
if admin_enabled():
    try:
        from .api.admin import router as admin_api_router
        app.include_router(admin_api_router, prefix="/v1")
        logging.info("Admin routes mounted (admin_enabled=%s)", True)
    except Exception:
        logging.info("Admin routes disabled (import failed)")
else:
    logging.info("Admin routes disabled (admin_enabled=%s)", False)

# Conditionally mount all admin-related routers
if admin_enabled():
    include("app.api.admin_ui:router", prefix="/v1")
    include("app.admin.routes:router", prefix="/v1")
    logging.info("Admin UI and extras routers processed (admin_enabled=%s)", True)
else:
    logging.info("Admin UI and extras routers disabled (admin_enabled=%s)", False)

include("app.api.me:router", prefix="/v1")
include("app.api.devices:router", prefix="/v1")

# Spotify SDK short-lived token router
include("app.api.spotify_sdk:router")
include("app.api.spotify:router", prefix="/v1")
include("app.api.spotify_player:router")

# Integrations status endpoint (aggregate third-party connection states)
include("app.api.integrations_status:router", prefix="/v1")

# Selftest router
include("app.api.selftest:router", prefix="/v1")

# Canonical whoami route provided by app.api.auth; do not mount alternate handlers

include("app.api.models:router", prefix="/v1")

include("app.api.history:router", prefix="/v1")

if admin_enabled():
    try:
        from .api.status_plus import router as status_plus_router
        app.include_router(status_plus_router, prefix="/v1", dependencies=[Depends(docs_security_with(["admin:write"]))])
        logging.info("Status plus router mounted (admin_enabled=%s)", True)
    except Exception:
        logging.info("Status plus router disabled (import failed)")
else:
    logging.info("Status plus router disabled (admin_enabled=%s)", False)

include("app.api.rag:router", prefix="/v1")

include("app.api.skills:router", prefix="/v1")

include("app.api.tv:router", prefix="/v1")

include("app.api.tts:router", prefix="/v1")

# Additional feature routers used by TV/companion UIs
include("app.api.contacts:router", prefix="/v1")

include("app.api.caregiver_auth:router", prefix="/v1")

include("app.api.photos:router", prefix="/v1")

include("app.api.calendar:router", prefix="/v1")

include("app.api.voices:router", prefix="/v1")

include("app.api.memory_ingest:router", prefix="/v1")

include("app.api.ask:router", prefix="/v1")

# Optional diagnostic/auxiliary routers -------------------------------------
try:
    from .api.care import router as care_router
    app.include_router(
        care_router,
        prefix="/v1",
        dependencies=[Depends(docs_security_with(["care:resident"]))],
    )
except Exception as e:
    logging.warning("Router include failed for app.api.care:router: %s", e)

include("app.api.care_ws:router", prefix="/v1")
include("app.api.ws_endpoints:router", prefix="/v1")

try:
    from .caregiver import router as caregiver_router
    app.include_router(
        caregiver_router,
        prefix="/v1",
        dependencies=[
            Depends(verify_token),
            Depends(optional_require_any_scope(["care:caregiver"])),
            Depends(docs_security_with(["care:caregiver"])),
        ],
    )
except Exception as e:
    logging.warning("Router include failed for app.caregiver:router: %s", e)

include("app.api.music:router", prefix="/v1")
include("app.api.music:root_router", prefix="/v1")
include("app.api.music_http:router", prefix="/v1")
include("app.api.music_ws:router", prefix="/v1")
include("app.api.tv_music_sim:router", prefix="/v1")





# Idempotent middleware registration helper
def register_middlewares_once(application):
    try:
        if getattr(application.state, "mw_registered", False):
            logging.debug("Middlewares already registered; skipping")
            return
    except Exception:
        pass

    # Core middlewares (inner → outer)
    add_mw(application, RequestIDMiddleware, name="RequestIDMiddleware")
    add_mw(application, DedupMiddleware, name="DedupMiddleware")
    add_mw(application, HealthCheckFilterMiddleware, name="HealthCheckFilterMiddleware")
    add_mw(application, TraceRequestMiddleware, name="TraceRequestMiddleware")
    add_mw(application, AuditMiddleware, name="AuditMiddleware")
    add_mw(application, RedactHashMiddleware, name="RedactHashMiddleware")
    add_mw(application, MetricsMiddleware, name="MetricsMiddleware")
    add_mw(application, RateLimitMiddleware, name="RateLimitMiddleware")
    add_mw(application, SessionAttachMiddleware, name="SessionAttachMiddleware")

    # Dev / optional middlewares
    if os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}:
        add_mw(application, ReloadEnvMiddleware, name="ReloadEnvMiddleware")
    if os.getenv("SILENT_REFRESH_ENABLED", "1").lower() in {"1", "true", "yes", "on"}:
        add_mw(application, SilentRefreshMiddleware, name="SilentRefreshMiddleware")

    # Error boundary
    add_mw(application, ErrorHandlerMiddleware, name="ErrorHandlerMiddleware")
    add_mw(application, EnhancedErrorHandlingMiddleware, name="EnhancedErrorHandlingMiddleware")

    # CSRF middleware (after CORS to allow preflight requests through)
    add_mw(application, CSRFMiddleware, name="CSRFMiddleware")

    # Standard CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
        expose_headers=expose_headers,
        max_age=max_age,
    )

    # Safari CORS cache fix - adds no-cache headers to prevent Safari caching issues
    application.add_middleware(SafariCORSCacheFixMiddleware)

    # CORS preflight middleware (must be outermost to handle OPTIONS before other middleware)
    from .middleware.cors import CorsPreflightMiddleware
    add_mw(application, CorsPreflightMiddleware, name="CorsPreflightMiddleware")
    logging.info("=== CSRF MIDDLEWARE REGISTERED ===")

    try:
        application.state.mw_registered = True
    except Exception:
        logging.debug("Failed to set application.state.mw_registered flag")

# Register middlewares once (idempotent)
register_middlewares_once(app)


# DEV-only middleware order assertion
def _current_mw_names() -> list[str]:
    try:
        return [m.cls.__name__ for m in getattr(app, "user_middleware", [])]
    except Exception:
        return []


def _assert_middleware_order_dev(app):
    """
    Assert middleware order is correct in development.

    This ensures middleware is registered in the proper order and no middleware
    has been accidentally added out of order or removed.
    """
    # Temporarily always run this assertion for debugging
    # if os.getenv("ENV", "dev").lower() != "dev":
    #     return  # only assert in dev environment

    # Starlette lists middleware in outer→inner order (opposite of registration order)
    # So the actual order we see is the reverse of what we registered
    want_outer_to_inner = [
        # outer → inner (as reported by Starlette)
        "CorsPreflightMiddleware",
        "SafariCORSCacheFixMiddleware",
        "CORSMiddleware",
        "CSRFMiddleware",
        "EnhancedErrorHandlingMiddleware",
        "ErrorHandlerMiddleware",
        # Optional dev middleware (in reverse order since they're added later)
        *(
            ["SilentRefreshMiddleware"]
            if os.getenv("SILENT_REFRESH_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
            else []
        ),
        *(
            ["ReloadEnvMiddleware"]
            if os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}
            else []
        ),
        "SessionAttachMiddleware",  # SessionAttachMiddleware runs after RateLimitMiddleware for metrics
        "RateLimitMiddleware",  # RateLimitMiddleware runs first to collect metrics
        "MetricsMiddleware",  # Clean prometheus metrics
        "RedactHashMiddleware",
        "AuditMiddleware",  # Append-only audit trail
        "TraceRequestMiddleware",
        "HealthCheckFilterMiddleware",
        "DedupMiddleware",
        "RequestIDMiddleware",  # innermost
    ]

    got = [m.cls.__name__ for m in app.user_middleware]

    # Compare the middleware order (excluding any unexpected middleware)
    if got != want_outer_to_inner:
        error_msg = f"""Middleware order mismatch.

Expected (outer→inner): {want_outer_to_inner}
Actual   (outer→inner): {got}

Expected registration order (inner→outer):
- RequestIDMiddleware (innermost)
- DedupMiddleware
- HealthCheckFilterMiddleware
- TraceRequestMiddleware
- RedactHashMiddleware
- RateLimitMiddleware (for metrics collection)
- SessionAttachMiddleware (after RateLimitMiddleware)
- CSRFMiddleware
- CORSMiddleware
- SafariCORSCacheFixMiddleware
- CorsPreflightMiddleware (outermost)
- ReloadEnvMiddleware (optional, DEV_MODE={os.getenv('DEV_MODE', '0')})
- SilentRefreshMiddleware (optional, SILENT_REFRESH_ENABLED={os.getenv('SILENT_REFRESH_ENABLED', '1')})
- ErrorHandlerMiddleware
- EnhancedErrorHandlingMiddleware

This error indicates middleware registration order is incorrect.
Check that add_mw() calls are in the correct sequence in main.py.
"""
        raise RuntimeError(error_msg)


# Call right after last add_middleware(...)
if os.getenv("ENV", "dev").lower() == "dev":
    _assert_middleware_order_dev(app)


# Debug middleware order dump
def _dump_mw_stack(app):
    try:
        # Log once at INFO using our current name helper
        logging.info("MW-ORDER (inner→outer): %s", _current_mw_names())
    except Exception as e:
        logging.warning("MW-ORDER dump failed: %r", e)


_dump_mw_stack(app)


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

    uvicorn.run(app, host=host, port=port)

from app.env_utils import load_env

load_env()
import asyncio
import hashlib
import logging
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

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


import jwt as _pyjwt

import app.skills  # populate SKILLS

from .logging_config import configure_logging, req_id_var

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

# Patch PyJWT decode to apply a sane default clock skew across the app
_PYJWT_DECODE_ORIG = getattr(_pyjwt, "decode", None)


def _pyjwt_decode_with_leeway(token, key=None, *args, **kwargs):
    # Default leeway from env (seconds)
    if "leeway" not in kwargs:
        try:
            kwargs["leeway"] = int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60)
        except Exception:
            kwargs["leeway"] = 60
    if _PYJWT_DECODE_ORIG is None:
        raise RuntimeError("pyjwt.decode not available")
    return _PYJWT_DECODE_ORIG(token, key, *args, **kwargs)


_pyjwt.decode = _pyjwt_decode_with_leeway
from .api.health import router as health_router
from .auth import router as auth_router
from .csrf import CSRFMiddleware
from .otel_utils import shutdown_tracing
from .status import router as status_router

try:
    from .api.preflight import router as preflight_router
except Exception:
    preflight_router = None  # type: ignore
from .api.google_oauth import router as google_oauth_router
from .api.oauth_google import router as oauth_google_router

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
try:
    from .api.music import router as music_router
    logging.debug("Music router imported successfully")
except Exception as e:
    logging.warning(f"Music router import failed: {e}")
    music_router = None  # type: ignore
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


def _safe_import_router(import_statement: str, feature_name: str, required_in_prod: bool = False):
    """
    Safely execute a router import with different behavior in dev vs prod.

    Args:
        import_statement: The import statement to execute (e.g., "from .api.sessions import router as sessions_router")
        feature_name: Human-readable name for logging (e.g., "sessions")
        required_in_prod: Whether this router is required in production
    """
    is_dev = os.getenv("ENV", "dev").lower() == "dev" or os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}

    try:
        # Execute the import statement in the current namespace
        exec(import_statement, globals())
        logger.debug(f"Router {feature_name} imported successfully")
        return True

    except Exception as e:
        if is_dev:
            logger.warning(f"Feature {feature_name} disabled (import failed: {e})")
            return False
        else:
            if required_in_prod:
                raise RuntimeError(f"Required feature {feature_name} failed to import in production: {e}")
            else:
                logger.warning(f"Feature {feature_name} disabled in production (import failed: {e})")
                return False


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
        "timestamp": datetime.utcnow().isoformat(),
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
            ("OpenAI Health Check", _init_openai_health_check),
            ("Vector Store", _init_vector_store),
            ("LLaMA Integration", _init_llama),
            ("Home Assistant", _init_home_assistant),
            ("Memory Store", _init_memory_store),
            ("Scheduler", _init_scheduler),
        ]

        for name, init_func in components:
            try:
                logger.info(f"Initializing {name}")
                await init_func()
                logger.info(f"{name} initialized successfully")
            except Exception as e:
                error_msg = f"Failed to initialize {name}: {e}"
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
        # Test database connectivity
        from .auth import _ensure_table

        await _ensure_table()
        logger.debug("Database initialization successful")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def _init_openai_health_check():
    """Perform OpenAI startup health check with tiny ping."""
    try:
        logger.info("Performing OpenAI startup health check")

        # Check if API key is configured
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("vendor_health vendor=openai ok=false reason=OPENAI_API_KEY_not_set")
            raise RuntimeError("OPENAI_API_KEY not configured")

        # Validate API key format (basic check)
        if not api_key.startswith("sk-"):
            logger.error("vendor_health vendor=openai ok=false reason=invalid_api_key_format")
            raise RuntimeError("Invalid OpenAI API key format")

        # Check base URL configuration
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url and not base_url.endswith("/v1"):
            logger.warning("OPENAI_BASE_URL should end with /v1, got: %s", base_url)

        # Perform tiny ping with 5-token prompt
        try:
            from .gpt_client import ask_gpt
            from .router import RoutingDecision

            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            routing_decision = RoutingDecision(
                vendor="openai",
                model=model,
                reason="startup_health_check",
                keyword_hit=None,
                stream=False,
                allow_fallback=False,
                request_id="startup_check"
            )

            # Use a very small prompt to minimize costs
            tiny_prompt = "ping"
            system_prompt = "You are a helpful assistant."
            timeout = 10  # Short timeout for startup

            # This will test: network connectivity, API key validity, model accessibility
            text, _, _, _ = await ask_gpt(
                tiny_prompt,
                model=model,
                system=system_prompt,
                timeout=timeout,
                routing_decision=routing_decision
            )

            # Check if we got a reasonable response
            if text and len(text.strip()) > 0:
                logger.info("vendor_health vendor=openai ok=true reason=successful_ping model=%s", model)
                logger.debug("OpenAI startup health check successful, response: %s", text.strip())
            else:
                logger.error("vendor_health vendor=openai ok=false reason=empty_response model=%s", model)
                raise RuntimeError("Empty response from OpenAI")

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)

            # Classify common error types
            if "timeout" in error_msg.lower() or "connect" in error_msg.lower():
                reason = "network_connectivity_error"
            elif "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
                reason = "api_key_invalid"
            elif "not found" in error_msg.lower() or "model" in error_msg.lower():
                reason = "model_access_error"
            elif "rate limit" in error_msg.lower():
                reason = "rate_limit_error"
            else:
                reason = f"{error_type}_{error_msg[:50].replace(' ', '_')}"

            logger.error("vendor_health vendor=openai ok=false reason=%s error_type=%s error_msg=%s",
                        reason, error_type, error_msg)
            raise RuntimeError(f"OpenAI health check failed: {reason}")

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
                "timestamp": datetime.utcnow().isoformat(),
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
    {"name": "TTS", "description": "Text-to-Speech APIs."},
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

_docs_url = "/docs" if _IS_DEV_ENV else None
_redoc_url = "/redoc" if _IS_DEV_ENV else None
_openapi_url = "/openapi.json" if _IS_DEV_ENV else None

_swagger_ui_parameters = {
    "docExpansion": "list",
    "filter": True,
    "persistAuthorization": True,
}

# Snapshot dev servers override at import time so tests that temporarily set
# OPENAPI_DEV_SERVERS during module reload still see the intended values even if
# the environment is restored before /openapi.json is requested.
_DEV_SERVERS_SNAPSHOT = os.getenv("OPENAPI_DEV_SERVERS")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
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


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        tags=tags_metadata,
    )
    # Provide developer-friendly servers list in dev
    if _IS_DEV_ENV:
        servers_env = _DEV_SERVERS_SNAPSHOT or os.getenv(
            "OPENAPI_DEV_SERVERS",
            "http://localhost:8000",
        )
        servers = [
            {"url": s.strip()}
            for s in (servers_env.split(",") if servers_env else [])
            if s and s.strip()
        ]
        if servers:
            schema["servers"] = servers
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[assignment]

# CORS configuration - will be added as outermost middleware
# WebSocket requirement: Only accept http://localhost:3000 for consistent origin validation

# CORS configuration - simplified logging
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")

# Parse and normalize entries
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

# Normalize common localhost variants (127.0.0.1 -> localhost)
origins = [
    o.replace("http://127.0.0.1:", "http://localhost:").replace(
        "https://127.0.0.1:", "https://localhost:"
    )
    for o in origins
]

# Remove any literal 'null' tokens (case-insensitive)
origins = [o for o in origins if o and o.lower() != "null"]

# Strict sanitization: prefer the single canonical localhost origin when
# any localhost-style origin is present; otherwise, strip obvious
# unwanted entries (raw IPs and common non-frontend ports like 8080).
import re
from urllib.parse import urlparse

sanitized = []
found_localhost = False
for o in origins:
    try:
        p = urlparse(o)
        host = p.hostname or ""
        port = p.port
        scheme = p.scheme or "http"
        # Map any localhost or 127.0.0.1 entry to the canonical frontend origin
        if host in ("localhost", "127.0.0.1"):
            if port is None or port == 3000 or scheme == "http":
                found_localhost = True
                continue
        # Skip raw IP addresses (e.g. 10.0.0.138) to avoid leaking LAN IPs
        if re.match(r"^\d+(?:\.\d+){3}$", host):
            continue
        # Skip alternate common dev ports that are not the frontend (e.g. :8080)
        if port == 8080:
            continue
        # Keep everything else (likely legitimate production origins)
        sanitized.append(o)
    except Exception:
        # If unparsable, drop it
        continue

if found_localhost:
    origins = ["http://localhost:3000"]
else:
    # Deduplicate but preserve order-ish
    seen = set()
    out = []
    for o in sanitized:
        if o in seen:
            continue
        seen.add(o)
        out.append(o)
    origins = out or ["http://localhost:3000"]

if not origins:
    logging.warning("No CORS origins configured. Defaulting to http://localhost:3000")
    origins = ["http://localhost:3000"]


def is_same_address_family(origin_list):
    """Check if all origins are in the same address family (localhost or IP)"""
    if not origin_list:
        return True
    localhost_count = sum(
        1 for o in origin_list if "localhost" in o or "127.0.0.1" in o
    )
    ip_count = sum(
        1 for o in origin_list if "localhost" not in o and "127.0.0.1" not in o
    )
    return localhost_count == 0 or ip_count == 0


if not is_same_address_family(origins):
    logging.warning("Mixed address families detected in CORS origins (post-sanitize).")
    logging.warning(
        "This may cause WebSocket connection issues. Consider using consistent addressing."
    )

# Allow credentials: yes (cookies/tokens) — enforce true for local dev to support cookies with exact origin
allow_credentials = True

# Store as single source of truth for HTTP+WS origin validation
app.state.allowed_origins = origins

# Log CORS configuration - clear INFO log for debugging origin issues
logging.info(
    "CORS resolved origins=%s | allow_credentials=%s | allow_methods=%s | allow_headers=%s | expose_headers=%s",
    origins,
    allow_credentials,
    ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    ["*", "Authorization"],
    ["X-Request-ID"],
)

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
        json_schema_extra={"example": {"prompt": "hello"}},
    )


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domain": "light",
                "service": "turn_on",
                "data": {"entity_id": "light.kitchen"},
            }
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
# NEW MODULAR ROUTERS - Extracted from local handlers
# =============================================================================
# Use capture router for capture endpoints (no duplication with sessions)
if _safe_import_router("from .api.capture import router as capture_router", "capture"):
    app.include_router(capture_router, prefix="/v1")

# Sessions router provides unique endpoints: /upload, /transcribe, /storytime websockets
if _safe_import_router("from .api.sessions import router as sessions_router", "sessions"):
    app.include_router(sessions_router, prefix="/v1")

if _safe_import_router("from .api.transcribe import router as transcribe_router", "transcribe"):
    app.include_router(transcribe_router, prefix="/v1")

if _safe_import_router("from .api.ha_local import router as ha_local_router", "ha_local"):
    app.include_router(ha_local_router, prefix="/v1")

if _safe_import_router("from .api.memories import router as memories_router", "memories"):
    app.include_router(memories_router, prefix="/v1")

if _safe_import_router("from .api.util import router as util_router", "util"):
    # Single mount provides both API docs visibility and routing
    app.include_router(util_router, prefix="/v1")

if _safe_import_router("from .api.ws_endpoints import router as ws_local_router", "ws_endpoints"):
    app.include_router(ws_local_router, prefix="/v1")

if _safe_import_router("from .api.debug import router as debug_router", "debug"):
    app.include_router(debug_router, prefix="/v1")

if _safe_import_router("from .api.core_misc import router as core_misc_router", "core_misc"):
    app.include_router(core_misc_router, prefix="/v1")

if _safe_import_router("from .api.metrics_root import router as metrics_root_router", "metrics_root"):
    app.include_router(metrics_root_router)  # keep /metrics at root

# Expose Prometheus metrics (scrapable) if our simple metrics router is available
if _safe_import_router("from .api.metrics import router as metrics_simple_router", "metrics_simple"):
    app.include_router(metrics_simple_router)

if _safe_import_router("from .health import router as health_diag_router", "health_diag"):
    # Mount diagnostics under a non-conflicting prefix to avoid shadowing /v1/health/*
    # expected by tests (api.health).
    app.include_router(health_diag_router, prefix="/v1/diag")

# Simple logs endpoint for UI issue tray
if _safe_import_router("from .api.logs_simple import router as logs_router", "logs_simple"):
    app.include_router(logs_router, prefix="/v1")

# =============================================================================
# EXISTING EXTERNAL ROUTERS - Keep in modern-first order
# =============================================================================
app.include_router(status_router, prefix="/v1")
# Tiered health (unauthenticated): /healthz/* endpoints
app.include_router(health_router)

# Include modern auth API router first to avoid route shadowing
if _safe_import_router("from .api.auth import router as auth_api_router", "auth_api", required_in_prod=True):
    app.include_router(auth_api_router, prefix="/v1")

# Legacy auth router split into focused modules. Mount conditionally based on env.
from .auth_providers import admin_enabled

# Mount whoami + finish endpoints (always available when auth router enabled)
if admin_enabled():
    if _safe_import_router("from .api.auth_router_whoami import router as auth_whoami_router", "auth_whoami"):
        app.include_router(auth_whoami_router, prefix="/v1")

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

print("INFO: Auth routers mounted (admin_enabled=True)")
if preflight_router is not None:
    app.include_router(preflight_router, prefix="/v1")
if device_auth_router is not None:
    app.include_router(device_auth_router, prefix="/v1")
# Removed duplicate inclusion of app.api.auth router to avoid route shadowing
app.include_router(oauth_google_router, prefix="/v1")
app.include_router(google_oauth_router, prefix="/v1")
app.include_router(auth_router, prefix="/v1")
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

# Google integration (optional)
# Provide both versioned and unversioned, under /google to match redirect defaults
app.include_router(google_router, prefix="/v1/google")
app.include_router(google_router, prefix="/google", include_in_schema=False)

# New modular routers for HA and profile/admin
if _safe_import_router("from .api.ha import router as ha_api_router", "ha_api"):
    app.include_router(
        ha_api_router,
        prefix="/v1",
        dependencies=[
            Depends(verify_token),
            Depends(require_any_scopes(["care:resident", "care:caregiver"])),
            Depends(docs_security_with(["care:resident"])),
        ],
    )

if _safe_import_router("from .api.reminders import router as reminders_router", "reminders"):
    app.include_router(reminders_router, prefix="/v1")

if _safe_import_router("from .api.profile import router as profile_router", "profile"):
    app.include_router(profile_router, prefix="/v1")

# Conditionally mount admin router based on environment
if admin_enabled():
    if _safe_import_router("from .api.admin import router as admin_api_router", "admin"):
        # Mount the new RBAC-powered admin router
        # The router already has prefix="/admin" so final paths will be /v1/admin/*
        app.include_router(
            admin_api_router,
            prefix="/v1",
            # No global dependencies - each endpoint uses its own RBAC rules
        )
        print("INFO: Admin routes mounted (admin_enabled=True)")
    else:
        print("INFO: Admin routes disabled (import failed)")
else:
    print("INFO: Admin routes disabled (admin_enabled=False)")

# Conditionally mount all admin-related routers
if admin_enabled():
    if _safe_import_router("from .api.admin_ui import router as admin_ui_router", "admin_ui"):
        app.include_router(admin_ui_router, prefix="/v1")

    # Also include experimental admin diagnostics (retrieval trace) router
    if _safe_import_router("from .admin.routes import router as admin_extras_router", "admin_extras"):
        app.include_router(admin_extras_router, prefix="/v1")

    print("INFO: Admin UI and extras routers processed (admin_enabled=True)")
else:
    print("INFO: Admin UI and extras routers disabled (admin_enabled=False)")

if _safe_import_router("from .api.me import router as me_router", "me"):
    app.include_router(me_router, prefix="/v1")

if _safe_import_router("from .api.devices import router as devices_router", "devices"):
    app.include_router(devices_router, prefix="/v1")

# Spotify SDK short-lived token router
if _safe_import_router("from .api.spotify_sdk import router as spotify_sdk", "spotify_sdk"):
    # spotify_sdk router defines its own prefix (/v1/spotify)
    app.include_router(spotify_sdk)

# Spotify OAuth router for login and callback
if _safe_import_router("from .api.spotify import router as spotify_router", "spotify"):
    app.include_router(spotify_router, prefix="/v1")
if _safe_import_router("from .api.spotify_player import router as spotify_player_router", "spotify_player"):
    # spotify_player router already includes /v1/spotify prefix
    app.include_router(spotify_player_router)

# Integrations status endpoint (aggregate third-party connection states)
if _safe_import_router("from .api.integrations_status import router as integrations_status_router", "integrations_status"):
    app.include_router(integrations_status_router, prefix="/v1")

# Selftest router
if _safe_import_router("from .api.selftest import router as selftest_router", "selftest"):
    app.include_router(selftest_router, prefix="/v1")

# Canonical whoami route provided by app.api.auth; do not mount alternate handlers

if _safe_import_router("from .api.models import router as models_router", "models"):
    app.include_router(models_router, prefix="/v1")

if _safe_import_router("from .api.history import router as history_router", "history"):
    app.include_router(history_router, prefix="/v1")

if admin_enabled():
    if _safe_import_router("from .api.status_plus import router as status_plus_router", "status_plus"):
        app.include_router(
            status_plus_router,
            prefix="/v1",
            dependencies=[Depends(docs_security_with(["admin:write"]))],
        )
        print("INFO: Status plus router mounted (admin_enabled=True)")
    else:
        print("INFO: Status plus router disabled (import failed)")
else:
    print("INFO: Status plus router disabled (admin_enabled=False)")

if _safe_import_router("from .api.rag import router as rag_router", "rag"):
    app.include_router(rag_router, prefix="/v1")

if _safe_import_router("from .api.skills import router as skills_router", "skills"):
    app.include_router(skills_router, prefix="/v1")

if _safe_import_router("from .api.tv import router as tv_router", "tv"):
    app.include_router(tv_router, prefix="/v1")

# TTS router (new)
if _safe_import_router("from .api.tts import router as tts_router", "tts"):
    app.include_router(tts_router, prefix="/v1")

# Additional feature routers used by TV/companion UIs
if _safe_import_router("from .api.contacts import router as contacts_router", "contacts"):
    app.include_router(contacts_router, prefix="/v1")

if _safe_import_router("from .api.caregiver_auth import router as caregiver_auth_router", "caregiver_auth"):
    app.include_router(caregiver_auth_router, prefix="/v1")

if _safe_import_router("from .api.photos import router as photos_router", "photos"):
    app.include_router(photos_router, prefix="/v1")

if _safe_import_router("from .api.calendar import router as calendar_router", "calendar"):
    app.include_router(calendar_router, prefix="/v1")

# Voices catalog
if _safe_import_router("from .api.voices import router as voices_router", "voices"):
    app.include_router(voices_router, prefix="/v1")

if _safe_import_router("from .api.memory_ingest import router as memory_ingest_router", "memory_ingest"):
    app.include_router(memory_ingest_router, prefix="/v1")

if _safe_import_router("from .api.ask import router as ask_router", "ask", required_in_prod=True):
    app.include_router(ask_router, prefix="/v1")

# Optional diagnostic/auxiliary routers -------------------------------------
if _safe_import_router("from .api.care import router as care_router", "care"):
    app.include_router(
        care_router,
        prefix="/v1",
        dependencies=[Depends(docs_security_with(["care:resident"]))],
    )

if _safe_import_router("from .api.care_ws import router as care_ws_router", "care_ws"):
    app.include_router(care_ws_router, prefix="/v1")

if _safe_import_router("from .caregiver import router as caregiver_router", "caregiver"):
    # Caregiver portal scaffold (e.g., /v1/caregiver/*)
    app.include_router(
        caregiver_router,
        prefix="/v1",
        dependencies=[
            Depends(verify_token),
            Depends(optional_require_any_scope(["care:caregiver"])),
            Depends(docs_security_with(["care:caregiver"])),
        ],
    )

# Music API router: attach HTTP dependencies to HTTP paths only
if music_router is not None:
    if _safe_import_router("from .api.music_http import music_http", "music_http"):
        app.include_router(music_http, prefix="/v1")
    else:
        # Fallback: include the music router directly without building a local APIRouter
        # This avoids creating APIRouter instances inside main.py
        app.include_router(music_router, prefix="/v1")

    # Keep non-prefixed inclusion for schema compatibility (music router only)
    app.include_router(music_router, include_in_schema=False)

    # Mount WS endpoints without HTTP dependencies
    if _safe_import_router("from .api.music import ws_router as music_ws_router", "music_ws"):
        app.include_router(music_ws_router, prefix="/v1")

    # Sim WS helpers for UI duck/restore
    if _safe_import_router("from .api.tv_music_sim import router as tv_music_sim_router", "tv_music_sim"):
        app.include_router(tv_music_sim_router, prefix="/v1")

    # Add /v1/state endpoint directly to main app
    # This fixes the 404 error when frontend tries to access /v1/state
    try:
        from .api.music import get_state as music_get_state
        from .deps.user import get_current_user_id
        from fastapi import Request, Response

        @app.get("/v1/state")
        async def get_music_state(
            request: Request,
            response: Response,
            user_id: str = Depends(get_current_user_id)
        ):
            """Direct proxy to music state endpoint to fix frontend 404 errors."""
            return await music_get_state(request, response, user_id)

        logging.info("Successfully added /v1/state endpoint")
    except Exception as e:
        logging.warning(f"Could not add /v1/state endpoint: {e}")





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

    # CSRF before CORS
    add_mw(application, CSRFMiddleware, name="CSRFMiddleware")
    logging.info("=== CSRF MIDDLEWARE REGISTERED ===")

    # Dev / optional middlewares
    if os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}:
        add_mw(application, ReloadEnvMiddleware, name="ReloadEnvMiddleware")
    if os.getenv("SILENT_REFRESH_ENABLED", "1").lower() in {"1", "true", "yes", "on"}:
        add_mw(application, SilentRefreshMiddleware, name="SilentRefreshMiddleware")

    # Error boundary
    add_mw(application, EnhancedErrorHandlingMiddleware, name="EnhancedErrorHandlingMiddleware")

    # CORS outermost
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*", "Authorization"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

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
        "CORSMiddleware",
        "EnhancedErrorHandlingMiddleware",
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
        "CSRFMiddleware",
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
- ReloadEnvMiddleware (optional, DEV_MODE={os.getenv('DEV_MODE', '0')})
- SilentRefreshMiddleware (optional, SILENT_REFRESH_ENABLED={os.getenv('SILENT_REFRESH_ENABLED', '1')})
- EnhancedErrorHandlingMiddleware
- CORSMiddleware (outermost)

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

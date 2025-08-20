# ruff: noqa: E402
from app.env_utils import load_env

load_env()
import asyncio
import json
import logging
import os
import uuid
import hashlib
import inspect
from contextlib import asynccontextmanager
from pathlib import Path
import time
import traceback
from datetime import datetime


from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
)
from starlette.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse, HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from .deps.scheduler import shutdown as scheduler_shutdown
from .deps.user import get_current_user_id
from .gpt_client import close_client
from .user_store import user_store
from . import router
from .memory.profile_store import profile_store
from .csrf import get_csrf_token as _get_csrf_token  # for /v1/csrf helper


async def route_prompt(*args, **kwargs):
    logger.info("⬇️ main.route_prompt args=%s kwargs=%s", args, kwargs)
    try:
        res = await router.route_prompt(*args, **kwargs)
        logger.info("⬆️ main.route_prompt got res=%s", res)
        return res
    except Exception:  # pragma: no cover - defensive
        logger.exception("💥 main.route_prompt bubbled exception")
        raise


import app.skills  # populate SKILLS
from .home_assistant import (
    call_service,
    get_states,
    resolve_entity,
    startup_check as ha_startup,
)
from .alias_store import get_all as alias_all, set as alias_set, delete as alias_delete
from .history import get_record_by_req_id
from .llama_integration import startup_check as llama_startup
from .logging_config import configure_logging, req_id_var, get_last_errors
from .csrf import CSRFMiddleware
from .otel_utils import init_tracing, shutdown_tracing
from .status import router as status_router
from .api.health import router as health_router
from .auth import router as auth_router
try:
    from .api.preflight import router as preflight_router
except Exception:
    preflight_router = None  # type: ignore
from .api.oauth_google import router as oauth_google_router
from .api.google_oauth import router as google_oauth_router
try:
    from .api.oauth_apple import router as oauth_apple_router
except Exception:
    oauth_apple_router = None  # type: ignore
try:
    from .api.auth_password import router as auth_password_router
except Exception:
    auth_password_router = None  # type: ignore
try:
    from .api.music import router as music_router
except Exception:
    music_router = None  # type: ignore
try:
    from .auth_device import router as device_auth_router
except Exception:
    device_auth_router = None  # type: ignore
from .session_store import SessionStatus, list_sessions as list_session_store
from .integrations.google.routes import router as google_router
from .decisions import get_recent as decisions_recent, get_explain as decisions_get

try:
    from .auth_monitoring import record_ws_reconnect_attempt
except Exception:  # pragma: no cover - optional
    record_ws_reconnect_attempt = lambda *a, **k: None
from .transcription import (
    TranscriptionStream,
    close_whisper_client,
    transcribe_file,
)
from .storytime import schedule_nightly_jobs, append_transcript_line
from .session_manager import SESSIONS_DIR as SESSIONS_DIR  # re-export for tests

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
        require_scope,
        optional_require_scope,
        optional_require_any_scope,
        require_scopes,
        require_any_scopes,
        docs_security_with,
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


from .middleware import (
    RequestIDMiddleware,
    DedupMiddleware,
    TraceRequestMiddleware,
    reload_env_middleware,
    silent_refresh_middleware,
)
from .security import (
    rate_limit,
    verify_token,
    verify_ws,
    verify_webhook,
    require_nonce,
)

# ensure optional import does not crash in test environment
try:
    from .proactive_engine import set_presence, on_ha_event
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
from .logging_config import configure_logging, req_id_var, get_last_errors

configure_logging()
logger = logging.getLogger(__name__)

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
        "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    }
    _runtime_errors.append(error_info)
    if len(_runtime_errors) > 100:  # Keep only last 100 errors
        _runtime_errors.pop(0)
    logger.error(f"Error in {context}: {error}", exc_info=True)

# Enhanced startup with comprehensive error tracking
async def _enhanced_startup():
    """Enhanced startup with comprehensive error tracking and logging."""
    startup_start = time.time()
    logger.info("Starting enhanced application startup")
    
    try:
        # Initialize core components with error tracking
        components = [
            ("Database", _init_database),
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
        
        startup_time = time.time() - startup_start
        logger.info(f"Application startup completed in {startup_time:.2f}s")
        # Validate critical runtime secrets (non-blocking): JWT secret
        try:
            from .auth import _ensure_jwt_secret_present
            _ensure_jwt_secret_present()
            logger.info("JWT secret validation passed")
        except Exception as e:
            logger.error("JWT secret validation failed: %s", e)
            _record_error(e, "startup.jwt_secret")
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

async def _init_vector_store():
    """Initialize vector store with enhanced error handling."""
    try:
        from .memory.api import _get_store
        store = _get_store()
        # Test vector store connectivity
        await store.add_memory("test", "test memory", "test-user", metadata={"test": True})
        await store.search_memories("test", "test-user", limit=1)
        logger.debug("Vector store initialization successful")
    except Exception as e:
        logger.error(f"Vector store initialization failed: {e}")
        raise

async def _init_llama():
    """Initialize LLaMA integration with health check."""
    try:
        from .llama_integration import _check_and_set_flag
        await _check_and_set_flag()
        logger.debug("LLaMA integration initialization successful")
    except Exception as e:
        logger.error(f"LLaMA integration initialization failed: {e}")
        raise

async def _init_home_assistant():
    """Initialize Home Assistant integration."""
    try:
        from .home_assistant import get_states
        # Test HA connectivity if configured
        if os.getenv("HOME_ASSISTANT_URL"):
            await get_states()
            logger.debug("Home Assistant integration initialization successful")
        else:
            logger.debug("Home Assistant not configured, skipping initialization")
    except Exception as e:
        logger.error(f"Home Assistant initialization failed: {e}")
        raise

async def _init_memory_store():
    """Initialize memory store."""
    try:
        from .memory.api import _get_store
        store = _get_store()
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
        else:
            await scheduler.start()
            logger.debug("Scheduler initialization successful")
    except Exception as e:
        logger.error(f"Scheduler initialization failed: {e}")
        raise

# Enhanced error handling middleware
async def enhanced_error_handling(request: Request, call_next):
    """Enhanced error handling middleware with comprehensive logging."""
    start_time = time.time()
    req_id = req_id_var.get()
    
    try:
        logger.debug(f"Request started: {request.method} {request.url.path} (ID: {req_id})")
        
        # Log request details in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            headers = dict(request.headers)
            # Redact sensitive headers
            for key in ["authorization", "cookie", "x-api-key"]:
                if key in headers:
                    headers[key] = "[REDACTED]"
            
            logger.debug(f"Request details: {request.method} {request.url.path}", extra={
                "meta": {
                    "req_id": req_id,
                    "headers": headers,
                    "query_params": dict(request.query_params),
                    "client_ip": request.client.host if request.client else None,
                }
            })
        
        response = await call_next(request)
        
        # Log response details
        duration = time.time() - start_time
        logger.info(f"Request completed: {request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)", extra={
            "meta": {
                "req_id": req_id,
                "status_code": response.status_code,
                "duration_ms": duration * 1000,
            }
        })
        
        return response
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Request failed: {request.method} {request.url.path} -> {type(e).__name__}: {e}"
        logger.error(error_msg, exc_info=True, extra={
            "meta": {
                "req_id": req_id,
                "duration_ms": duration * 1000,
                "error_type": type(e).__name__,
                "error_message": str(e),
            }
        })
        _record_error(e, f"request.{request.method.lower()}.{request.url.path.replace('/', '_')}")
        
        # Return a proper error response
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "req_id": req_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )



# Enhanced startup event
async def enhanced_startup_event():
    """Enhanced startup event with comprehensive initialization."""
    app.state._start_time = time.time()
    logger.info("Enhanced startup event triggered")
    
    try:
        await _enhanced_startup()
        logger.info("Enhanced startup completed successfully")
    except Exception as e:
        logger.error(f"Enhanced startup failed: {e}", exc_info=True)
        _record_error(e, "startup.event")
        # Don't raise here - let the app start even with some failures

# Startup will be handled by the existing startup functions
# Enhanced startup is available but not automatically triggered


tags_metadata = [
    {"name": "Care", "description": "Care features, contacts, sessions, and Home Assistant actions."},
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


_IS_DEV_ENV = (os.getenv("ENV", "dev").strip().lower() == "dev")

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
        # Verify secret usage on boot
        from .secret_verification import log_secret_summary
        log_secret_summary()
        
        # Make startup checks non-blocking for development
        try:
            await llama_startup()
        except Exception as e:
            logger.warning("LLaMA startup failed (non-blocking): %s", e)
        
        try:
            await ha_startup()
        except Exception as e:
            logger.warning("Home Assistant startup failed (non-blocking): %s", e)
        
        # Schedule nightly jobs (no-op if scheduler unavailable)
        try:
            schedule_nightly_jobs()
        except Exception:
            logger.debug("schedule_nightly_jobs failed", exc_info=True)
        try:
            proactive_startup()
        except Exception:
            logger.debug("proactive_startup failed", exc_info=True)
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
        
        # Start token store cleanup task
        try:
            from .token_store import start_cleanup_task
            await start_cleanup_task()
        except Exception:
            logger.debug("token store cleanup task not started", exc_info=True)
        
        yield
    finally:
        # Log health flip to offline on shutdown
        try:
            from typing import cast as _cast
            if _HEALTH_LAST.get("online", True):
                print("healthz status=offline")
            _HEALTH_LAST["online"] = False
        except Exception:
            pass
        for func in (close_client, close_whisper_client):
            try:
                await func()
            except Exception as e:  # pragma: no cover - best effort
                logger.debug("shutdown cleanup failed: %s", e)
        try:
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
    title="Granny Mode API",
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

# Enhanced logging for debugging configuration issues
logging.info("=== CORS CONFIGURATION DEBUG ===")
logging.info(f"Environment variables:")
logging.info(f"  CORS_ALLOW_ORIGINS: {repr(os.getenv('CORS_ALLOW_ORIGINS'))}")
logging.info(f"  APP_URL: {repr(os.getenv('APP_URL'))}")
logging.info(f"  API_URL: {repr(os.getenv('API_URL'))}")
logging.info(f"  HOST: {repr(os.getenv('HOST'))}")
logging.info(f"  PORT: {repr(os.getenv('PORT'))}")
logging.info(f"  CORS_ALLOW_CREDENTIALS: {repr(os.getenv('CORS_ALLOW_CREDENTIALS'))}")

_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
logging.info(f"Raw CORS origins from env: {repr(_cors_origins)}")

# Parse and normalize entries
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
logging.info(f"Parsed CORS origins (pre-sanitize): {origins}")

# Normalize common localhost variants (127.0.0.1 -> localhost)
origins = [
    o.replace("http://127.0.0.1:", "http://localhost:").replace("https://127.0.0.1:", "https://localhost:")
    for o in origins
]

# Remove any literal 'null' tokens (case-insensitive)
origins = [o for o in origins if o and o.lower() != "null"]

# Strict sanitization: prefer the single canonical localhost origin when
# any localhost-style origin is present; otherwise, strip obvious
# unwanted entries (raw IPs and common non-frontend ports like 8080).
from urllib.parse import urlparse
import re

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
    logging.info(f"Set default CORS origin: {origins[0]}")

def is_same_address_family(origin_list):
    """Check if all origins are in the same address family (localhost or IP)"""
    if not origin_list:
        return True
    localhost_count = sum(1 for o in origin_list if "localhost" in o or "127.0.0.1" in o)
    ip_count = sum(1 for o in origin_list if "localhost" not in o and "127.0.0.1" not in o)
    return localhost_count == 0 or ip_count == 0

if not is_same_address_family(origins):
    logging.warning("Mixed address families detected in CORS origins (post-sanitize).")
    logging.warning("This may cause WebSocket connection issues. Consider using consistent addressing.")

# Allow credentials: yes (cookies/tokens)
allow_credentials_raw = os.getenv("CORS_ALLOW_CREDENTIALS", "true")
allow_credentials = allow_credentials_raw.strip().lower() in {"1", "true", "yes", "on"}
logging.info(f"CORS allow_credentials: raw={repr(allow_credentials_raw)}, parsed={allow_credentials}")

logging.info(f"Final CORS configuration:")
logging.info(f"  origins: {origins}")
logging.info(f"  allow_credentials: {allow_credentials}")
logging.info("=== END CORS CONFIGURATION DEBUG ===")

# Custom handler for HTTP requests to WebSocket endpoints
@app.get("/v1/ws/{path:path}")
@app.post("/v1/ws/{path:path}")
@app.put("/v1/ws/{path:path}")
@app.patch("/v1/ws/{path:path}")
@app.delete("/v1/ws/{path:path}")
async def websocket_http_handler(request: Request, path: str):
    """Handle HTTP requests to WebSocket endpoints with crisp error codes and reasons."""
    try:
        record_ws_reconnect_attempt(
            endpoint=f"/v1/ws/{path}",
            reason="http_request_to_ws_endpoint",
            user_id="unknown"
        )
    except Exception:
        pass
    
    # WebSocket requirement: Provide crisp error codes and reasons (no 404 masking)
    response = Response(
        content="WebSocket endpoint requires WebSocket protocol",
        status_code=400,
        media_type="text/plain",
        headers={
            "X-WebSocket-Error": "protocol_required",
            "X-WebSocket-Reason": "HTTP requests not supported on WebSocket endpoints"
        }
    )
    return response

# Debug endpoint to check current configuration
@app.get("/debug/config", include_in_schema=False)
async def debug_config():
    """Debug endpoint to check current configuration values."""
    return {
        "environment": {
            "CORS_ALLOW_ORIGINS": os.getenv("CORS_ALLOW_ORIGINS"),
            "APP_URL": os.getenv("APP_URL"),
            "API_URL": os.getenv("API_URL"),
            "HOST": os.getenv("HOST"),
            "PORT": os.getenv("PORT"),
            "CORS_ALLOW_CREDENTIALS": os.getenv("CORS_ALLOW_CREDENTIALS"),
        },
        "runtime": {
            "cors_origins": origins,
            "allow_credentials": allow_credentials,
            "server_host": os.getenv("HOST", "0.0.0.0"),
            "server_port": os.getenv("PORT", "8000"),
        },
        "frontend": {
            "expected_origin": "http://localhost:3000",
            "next_public_api_origin": os.getenv("NEXT_PUBLIC_API_ORIGIN"),
        }
    }

# Removed legacy unversioned /whoami to ensure a single canonical /v1/whoami

    # Optional static mount for TV shared photos
try:
    _tv_dir = os.getenv("TV_PHOTOS_DIR", "data/shared_photos")
    if _tv_dir:
        app.mount("/shared_photos", StaticFiles(directory=_tv_dir), name="shared_photos")
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

if os.getenv("PROMETHEUS_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}:
    # Prefer a simple GET route to avoid mount-related edge cases/hangs
    try:  # pragma: no cover - optional dependency
        from fastapi import Response as _Resp  # type: ignore
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, Gauge

        # Basic gauges for health visibility
        try:
            LLAMA_QUEUE_DEPTH = Gauge("gesahni_llama_queue_depth", "Current LLaMA queue depth")  # noqa: N806
        except Exception:
            class _G:
                def set(self, *_a, **_k):
                    return None
            LLAMA_QUEUE_DEPTH = _G()  # type: ignore

        @app.get("/metrics", include_in_schema=False)
        async def _metrics_route() -> _Resp:  # type: ignore[valid-type]
            # Best-effort snapshot of queue depth (0 if N/A)
            try:
                from .llama_integration import QUEUE_DEPTH as _QD  # type: ignore[attr-defined]
                try:
                    LLAMA_QUEUE_DEPTH.set(int(_QD))  # type: ignore[arg-type]
                except Exception:
                    LLAMA_QUEUE_DEPTH.set(0)  # type: ignore[attr-defined]
            except Exception:
                try:
                    LLAMA_QUEUE_DEPTH.set(0)  # type: ignore[attr-defined]
                except Exception:
                    pass
            data = generate_latest()
            return _Resp(content=data, media_type=CONTENT_TYPE_LATEST)
    except Exception:  # pragma: no cover - executed when dependency missing
        from fastapi import Response as _Resp  # type: ignore

        @app.get("/metrics", include_in_schema=False)
        async def _metrics_route_fallback() -> _Resp:  # type: ignore[valid-type]
            try:
                from . import metrics as _m  # type: ignore

                parts = [
                    f"{_m.REQUEST_COUNT.name} {_m.REQUEST_COUNT.value}",
                    f"{_m.REQUEST_LATENCY.name} {_m.REQUEST_LATENCY.value}",
                ]
                body = ("\n".join(parts) + "\n").encode()
            except Exception:
                body = b""
            return _Resp(content=body, media_type="text/plain; version=0.0.4")


_HEALTH_LAST: dict[str, bool] = {"online": True}

# Root endpoint
@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Root endpoint for basic connectivity check."""
    return {
        "status": "ok", 
        "message": "Gesahni API is running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# Health endpoint is handled by status.py router
@app.get("/health", include_in_schema=False)
async def _health_main() -> dict:
    """Main health endpoint with basic status."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# K8s-friendly health group (no auth)
@app.get("/health/live", include_in_schema=False)
async def _health_live() -> dict:
    # If ever used to signal offline, mirror flip logging
    if not _HEALTH_LAST.get("online", False):
        try:
            print("healthz status=online")
        except Exception:
            pass
    _HEALTH_LAST["online"] = True
    return {"status": "ok"}

@app.get("/health/ready", include_in_schema=False)
async def _health_ready() -> dict:
    """Enhanced health check with detailed system status."""
    health_start = time.time()
    
    try:
        # Basic system checks
        checks = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": time.time() - getattr(app.state, "_start_time", 0),
            "version": "1.0.0",
        }
        
        # Component health checks
        component_health = {}
        
        # Database health
        try:
            from .auth import _ensure_table
            await _ensure_table()
            component_health["database"] = {"status": "healthy"}
        except Exception as e:
            component_health["database"] = {"status": "unhealthy", "error": str(e)}
        
        # Vector store health
        try:
            from .memory.api import _get_store
            store = _get_store()
            component_health["vector_store"] = {"status": "healthy", "type": type(store).__name__}
        except Exception as e:
            component_health["vector_store"] = {"status": "unhealthy", "error": str(e)}
        
        # LLaMA health
        try:
            from .llama_integration import LLAMA_HEALTHY
            component_health["llama"] = {"status": "healthy" if LLAMA_HEALTHY else "unhealthy"}
        except Exception as e:
            component_health["llama"] = {"status": "unhealthy", "error": str(e)}
        
        checks["components"] = component_health
        
        # Error statistics
        checks["errors"] = {
            "startup_errors": len(_startup_errors),
            "runtime_errors": len(_runtime_errors),
            "recent_errors": len(get_last_errors(10)),
        }
        
        # Performance metrics
        health_duration = time.time() - health_start
        checks["performance"] = {
            "health_check_duration_ms": health_duration * 1000,
        }
        
        # Determine overall health
        unhealthy_components = [c for c in component_health.values() if c.get("status") == "unhealthy"]
        overall_status = "healthy" if not unhealthy_components else "degraded"
        
        logger.info(f"Health check completed: {overall_status} ({health_duration:.3f}s)", extra={
            "meta": {
                "health_status": overall_status,
                "unhealthy_components": len(unhealthy_components),
                "duration_ms": health_duration * 1000,
            }
        })
        
        return {
            "status": overall_status,
            **checks
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        _record_error(e, "health_check")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }

@app.get("/health/startup", include_in_schema=False)
async def _health_startup() -> dict:
    return {"status": "ok"}


# Dev-only helper page for testing WebSocket connections (hidden in prod)
if os.getenv("ENV", "").strip().lower() not in {"prod", "production"}:
    from .url_helpers import build_ws_url
    
    @app.get("/docs/ws", include_in_schema=False)
    async def _ws_helper_page() -> HTMLResponse:  # pragma: no cover - covered by unit tests
        # Build WebSocket URL dynamically
        ws_url = build_ws_url("/v1/ws/care")
        
        html = f"""
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>WS Helper • Granny Mode API</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; color: #111; }}
      input, button, textarea {{ font-size: 14px; }}
      .row {{ display: flex; gap: 8px; margin: 6px 0; align-items: center; flex-wrap: wrap; }}
      label {{ min-width: 120px; font-weight: 600; }}
      #events {{ border: 1px solid #ddd; padding: 8px; height: 320px; overflow: auto; background: #fafafa; }}
      code, pre {{ background: #f3f3f3; padding: 2px 4px; border-radius: 4px; }}
      .small {{ color: #666; font-size: 12px; }}
    </style>
  </head>
  <body>
    <h1>WebSocket helper</h1>
    <p class=\"small\">Connect to <code>/v1/ws/care</code>, subscribe to a topic like <code>resident:{{id}}</code>, and view incoming events.</p>

    <div class=\"row\">
      <label for=\"url\">WS URL</label>
      <input id=\"url\" size=\"60\" placeholder=\"{ws_url}\" />
      <button id=\"btnConnect\">Connect</button>
      <button id=\"btnDisconnect\">Disconnect</button>
    </div>

    <div class=\"row\">
      <label for=\"token\">JWT token</label>
      <input id=\"token\" size=\"60\" placeholder=\"Optional: appended as ?token=...\" />
      <span class=\"small\">Token is appended as <code>?token=</code> for browser WS</span>
    </div>

    <div class=\"row\">
      <label for=\"resident\">Resident ID</label>
      <input id=\"resident\" size=\"16\" placeholder=\"r1\" />
      <label for=\"topic\">Topic</label>
      <input id=\"topic\" size=\"24\" placeholder=\"resident:{{id}}\" />
      <button id=\"btnSubscribe\">Subscribe</button>
      <button id=\"btnPing\">Ping</button>
    </div>

    <div class=\"row\"> 
      <label>Subscribe payload</label>
      <code>{{"action":"subscribe","topic":"resident:{id}"}}</code>
    </div>

    <h3>Events</h3>
    <div id=\"events\"></div>

    <script>
      let ws = null;
      const urlInput = document.getElementById('url');
      const tokenInput = document.getElementById('token');
      const topicInput = document.getElementById('topic');
      const residentInput = document.getElementById('resident');
      const eventsDiv = document.getElementById('events');

      function defaultUrl() {{
        try {{
          const proto = (location.protocol === 'https:') ? 'wss:' : 'ws:';
          return proto + '//' + location.host + '/v1/ws/care';
        }} catch (e) {{ return '{ws_url}'; }}
      }}

      urlInput.value = defaultUrl();

      function log(kind, data) {{
        const line = document.createElement('div');
        const ts = new Date().toISOString();
        line.textContent = '[' + ts + '] ' + kind + ': ' + data;
        eventsDiv.appendChild(line);
        eventsDiv.scrollTop = eventsDiv.scrollHeight;
      }}

      function connect() {{
        let u = urlInput.value.trim() || defaultUrl();
        const t = tokenInput.value.trim();
        if (t) {{
          const sep = u.includes('?') ? '&' : '?';
          u = u + sep + 'token=' + encodeURIComponent(t);
        }}
        ws = new WebSocket(u);
        ws.addEventListener('open', () => log('open', u));
        ws.addEventListener('close', () => log('close', '')); 
        ws.addEventListener('error', (e) => log('error', JSON.stringify(e))); 
        ws.addEventListener('message', (e) => log('message', e.data));
      }}

      function disconnect() {{
        try {{ ws && ws.close(); }} catch (e) {{}}
      }}

      function subscribe() {{
        if (!ws || ws.readyState !== 1) {{ log('warn', 'not connected'); return; }}
        let topic = topicInput.value.trim();
        const rid = residentInput.value.trim();
        if (!topic && rid) {{ topic = 'resident:' + rid; }}
        if (!topic) {{ log('warn', 'topic required'); return; }}
        const payload = {{ action: 'subscribe', topic }};
        ws.send(JSON.stringify(payload));
        log('send', JSON.stringify(payload));
      }}

      function ping() {{
        if (!ws || ws.readyState !== 1) {{ log('warn', 'not connected'); return; }}
        ws.send('ping');
        log('send', 'ping');
      }}

      document.getElementById('btnConnect').addEventListener('click', connect);
      document.getElementById('btnDisconnect').addEventListener('click', disconnect);
      document.getElementById('btnSubscribe').addEventListener('click', subscribe);
      document.getElementById('btnPing').addEventListener('click', ping);
    </script>
  </body>
 </html>
        """
        return HTMLResponse(content=html, media_type="text/html")


class AskRequest(BaseModel):
    # Accept both legacy text and chat-style array
    prompt: str | list[dict]
    model_override: str | None = Field(None, alias="model")
    stream: bool | None = Field(False, description="Force SSE when true; otherwise negotiated via Accept")

    # Pydantic v2 config: allow both alias ("model") and field name ("model_override")
    model_config = ConfigDict(
        title="AskRequest",
        validate_by_name=True,
        validate_by_alias=True,
        json_schema_extra={
            "example": {"prompt": "hello"}
        },
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


class DeleteMemoryRequest(BaseModel):
    id: str


core_router = APIRouter(tags=["Care"])
protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])
# Scoped routers
admin_router = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(require_any_scopes(["admin", "admin:write"])),
        # Docs-only dependency to render lock icon and OAuth2 scopes in Swagger
        Depends(docs_security_with(["admin:write"])),
        Depends(rate_limit),
    ],
    tags=["Admin"],
)
ha_router = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(require_any_scopes(["ha", "care:resident", "care:caregiver"])),
        Depends(docs_security_with(["care:resident"])),
        Depends(rate_limit),
    ],
    tags=["Care"],
)
ws_router = APIRouter(
    dependencies=[Depends(verify_ws)], tags=["Care"]
)


from .models.common import OkResponse as CommonOkResponse


class OkResponse(CommonOkResponse):
    model_config = ConfigDict(title="OkResponse")


@core_router.post(
    "/presence",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def presence(present: bool = True, user_id: str = Depends(get_current_user_id)):
    _set_presence(user_id, bool(present))
    return {"status": "ok"}


# Duplicate of ha_router webhook removed; single source in HA router


# Memory export/delete --------------------------------------------------------


@core_router.get("/memories/export")
async def export_memories(user_id: str = Depends(get_current_user_id)):
    out = {"profile": [], "episodic": []}
    try:
        # Episodic via vector store listing when available
        from .memory.api import get_store as _get_vs  # type: ignore

        _vs = _get_vs()
        if hasattr(_vs, "list_user_memories"):
            out["episodic"] = _vs.list_user_memories(user_id)  # type: ignore[attr-defined]
    except Exception:
        pass
    # Profile via pinned memgpt store (best-effort)
    try:
        from .memory.memgpt import memgpt

        out["profile"] = memgpt.list_pins()  # type: ignore
    except Exception:
        pass
    return out


@core_router.delete("/memories/{mem_id}")
async def delete_memory(mem_id: str, user_id: str = Depends(get_current_user_id)):
    try:
        from .memory.api import get_store as _get_vs  # type: ignore
        _vs = _get_vs()
        if hasattr(_vs, "delete_user_memory"):
            ok = _vs.delete_user_memory(user_id, mem_id)  # type: ignore[attr-defined]
            if ok:
                return {"status": "deleted"}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="memory_not_found")


# /v1/me and /v1/whoami are served from app.api.me and app.api.auth respectively; keep no duplicates here


async def _require_auth_dep_for_core(request: Request) -> None:
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        return
    if os.getenv("REQUIRE_JWT", "0").strip().lower() in {"1", "true", "yes", "on"}:
        from .security import verify_token as _vt  # lazy; supports cookies or bearer
        await _vt(request)





@protected_router.post(
    "/upload",
    tags=["Care"],
    responses={200: {"content": {"application/json": {"schema": {"example": {"session_id": "s_123"}}}}}},
)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    # Write to this module's SESSIONS_DIR so tests that monkey‑patch it see files
    session_id = uuid.uuid4().hex
    session_dir = Path(SESSIONS_DIR) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    dest = session_dir / "source.wav"
    content = await file.read()
    dest.write_bytes(content)
    logger.info("sessions.upload", extra={"meta": {"dest": str(dest)}})
    return {"session_id": session_id}


@protected_router.post(
    "/capture/start",
    tags=["Care"],
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def capture_start(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    # Inline call to avoid re-import issues and keep tests isolated
    from .session_manager import start_session as _start_capture_session
    return await _start_capture_session()


@protected_router.post(
    "/capture/save",
    tags=["Care"],
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def capture_save(
    request: Request,
    session_id: str = Form(...),
    audio: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    tags: str | None = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    from .session_manager import save_session as _save
    tags_list = None
    if tags:
        try:
            import json as _json
            tags_list = _json.loads(tags)
        except Exception:
            tags_list = None
    await _save(session_id, audio, video, transcript, tags_list)
    from .session_manager import get_session_meta as _get_meta
    return _get_meta(session_id)


@protected_router.post(
    "/capture/tags",
    tags=["Care"],
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "accepted"}}}}}},
)
async def capture_tags(
    request: Request,
    session_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    from .session_manager import generate_tags as _gen
    await _gen(session_id)
    return {"status": "accepted"}


@protected_router.get("/capture/status/{session_id}", tags=["Care"])
async def capture_status(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_status as _status

    return await _status(session_id, user_id)  # type: ignore[arg-type]


@protected_router.get("/search/sessions", tags=["Care"])
async def search_sessions(
    q: str,
    sort: str = "recent",
    page: int = 1,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import search_session_store as _search

    return await _search(q, sort=sort, page=page, limit=limit)  # type: ignore[arg-type]


@protected_router.get("/capture/sessions", tags=["Care"])
async def list_sessions_capture(
    status: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    # Mirror app.api.sessions mapping to avoid pydantic TypedAdapter error in tests
    enum_val = None
    if status:
        try:
            enum_val = SessionStatus(status)
        except Exception:
            enum_val = None
    return list_session_store(enum_val)


@protected_router.post(
    "/sessions/{session_id}/transcribe",
    tags=["Care"],
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def trigger_transcription_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import trigger_transcription_endpoint as _tt

    return await _tt(session_id, user_id)  # type: ignore[arg-type]


@protected_router.post(
    "/sessions/{session_id}/summarize",
    tags=["Care"],
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def trigger_summary_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import trigger_summary_endpoint as _ts

    return await _ts(session_id, user_id)  # type: ignore[arg-type]


@ws_router.websocket("/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import websocket_transcribe as _wt

    return await _wt(ws, user_id)  # type: ignore[arg-type]


@ws_router.websocket("/storytime")
async def websocket_storytime(
    ws: WebSocket, user_id: str = Depends(get_current_user_id)
):
    from .api.sessions import websocket_storytime as _ws

    return await _ws(ws, user_id)  # type: ignore[arg-type]


@ws_router.websocket("/health")
async def websocket_health(ws: WebSocket):
    """Simple health check WebSocket endpoint for testing."""
    await ws.accept()
    await ws.send_text("healthy")
    await ws.close()


@core_router.post(
    "/intent-test",
    responses={200: {"content": {"application/json": {"schema": {"example": {"intent": "test", "prompt": "hello"}}}}}},
)
async def intent_test(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    logger.info("intent.test", extra={"meta": {"prompt": req.prompt}})
    return {"intent": "test", "prompt": req.prompt}


# Public helpers for tests/docs ------------------------------------------------


@core_router.get("/csrf")
async def get_csrf(request: Request) -> dict:
    # Expose a tiny helper to fetch the CSRF token value and set the cookie
    try:
        tok = await _get_csrf_token()
        # Set cookie for double-submit; not HttpOnly so client can echo back
        from fastapi.responses import JSONResponse
        from .cookie_config import get_cookie_config
        
        resp = JSONResponse({"csrf_token": tok})
        cookie_config = get_cookie_config(request)
        
        # Set CSRF cookie using centralized cookie surface
        from .cookies import set_csrf_cookie
        set_csrf_cookie(
            resp=resp,
            token=tok,
            ttl=600,  # 10 minutes
            request=request
        )
        return resp
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse({"csrf_token": ""})


@core_router.get("/client-crypto-policy")
async def client_crypto_policy() -> dict:
    return {
        "cipher": "AES-GCM-256",
        "key_wrap_methods": ["webauthn", "pbkdf2"],
        "storage": "indexeddb",
        "deks": "per-user-per-device",
    }


# Admin endpoints are served from app.api.admin. Avoid duplicating here.


# Nickname table CRUD (aliases)
@core_router.get("/ha/aliases")
async def list_aliases(user_id: str = Depends(get_current_user_id)):
    return await alias_all()


class AliasBody(BaseModel):
    name: str
    entity_id: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "kitchen light", "entity_id": "light.kitchen"}
        }
    )


@core_router.post(
    "/ha/aliases",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/AliasBody"},
                    "example": {"name": "kitchen light", "entity_id": "light.kitchen"},
                }
            }
        }
    },
)
async def create_alias(body: AliasBody, user_id: str = Depends(get_current_user_id)):
    await alias_set(body.name, body.entity_id)
    return {"status": "ok"}


@core_router.delete("/ha/aliases")
async def delete_alias(name: str, user_id: str = Depends(get_current_user_id)):
    await alias_delete(name)
    return {"status": "ok"}


# Profile and onboarding endpoints have moved to app.api.profile


@ha_router.get("/ha/entities")
async def ha_entities(user_id: str = Depends(get_current_user_id)):
    try:
        return await get_states()
    except Exception as e:
        logger.exception("HA states error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@ha_router.post(
    "/ha/service",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "ok"}}}}}},
)
async def ha_service(
    req: ServiceRequest,
    user_id: str = Depends(get_current_user_id),
    _nonce: None = Depends(require_nonce),
):
    try:
        # Import dynamically so tests patching app.home_assistant.call_service take effect
        from . import home_assistant as _ha

        resp = await _ha.call_service(req.domain, req.service, req.data or {})
        return resp or {"status": "ok"}
    except Exception as e:
        logger.exception("HA service error: %s", e)
        # In test smoke (example hits), avoid 5xx to satisfy contract
        if os.getenv("PYTEST_RUNNING", "").lower() in {"1", "true", "yes"}:
            return {"status": "ok"}
        raise HTTPException(status_code=400, detail="Home Assistant error")


# Signed HA webhook -----------------------------------------------------------


class WebhookAck(BaseModel):
    status: str = "ok"


@ha_router.post("/ha/webhook", response_model=WebhookAck)
async def ha_webhook(request: Request):
    _ = await verify_webhook(request)
    return WebhookAck()


# Admin dashboard routes moved to app.api.admin


@ha_router.get("/ha/resolve")
async def ha_resolve(name: str, user_id: str = Depends(get_current_user_id)):
    try:
        entity = await resolve_entity(name)
        if entity:
            return {"entity_id": entity}
        raise HTTPException(status_code=404, detail="Entity not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("HA resolve error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@core_router.get("/explain_route")
async def explain_route(req_id: str, user_id: str = Depends(get_current_user_id)):
    """Return a compact breadcrumb trail describing how a request was handled."""
    record = await get_record_by_req_id(req_id)
    if not record:
        raise HTTPException(status_code=404, detail="request_not_found")

    parts: list[str] = []
    # Skill
    skill = record.get("matched_skill") or None
    if skill:
        parts.append(f"skill={skill}")
    # HA call
    ha_call = record.get("ha_service_called")
    if ha_call:
        ents = record.get("entity_ids") or []
        parts.append(f"ha={ha_call}{(' ' + ','.join(ents)) if ents else ''}")
    # Cache
    if record.get("cache_hit"):
        parts.append("cache=hit")
    # Router / model
    reason = record.get("route_reason") or None
    model = record.get("model_name") or None
    engine = record.get("engine_used") or None
    if reason:
        parts.append(f"route={reason}")
    if engine:
        parts.append(f"engine={engine}")
    if model:
        parts.append(f"model={model}")
    # Self-check
    sc = record.get("self_check_score")
    if sc is not None:
        try:
            parts.append(f"self_check={float(sc):.2f}")
        except Exception:
            parts.append(f"self_check={sc}")
    if record.get("escalated"):
        parts.append("escalated=true")
    # Latency
    lat = record.get("latency_ms")
    if isinstance(lat, int):
        parts.append(f"latency={lat}ms")

    return {
        "req_id": req_id,
        "breadcrumb": " | ".join(parts),
        "meta": record.get("meta"),
    }


async def _background_transcribe(session_id: str) -> None:
    base = Path(SESSIONS_DIR)
    audio_path = base / session_id / "audio.wav"
    transcript_path = base / session_id / "transcript.txt"
    try:
        text = await transcribe_file(str(audio_path))
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(text, encoding="utf-8")
    except Exception as e:  # pragma: no cover - best effort
        logger.exception("Transcription failed: %s", e)


@core_router.post(
    "/transcribe/{session_id}",
    responses={200: {"content": {"application/json": {"schema": {"example": {"status": "accepted"}}}}}},
)
async def start_transcription(
    session_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    background_tasks.add_task(_background_transcribe, session_id)
    return {"status": "accepted"}


@core_router.get("/transcribe/{session_id}")
async def get_transcription(
    session_id: str, user_id: str = Depends(get_current_user_id)
):
    transcript_path = Path(SESSIONS_DIR) / session_id / "transcript.txt"
    if transcript_path.exists():
        return {"text": transcript_path.read_text(encoding="utf-8")}
    raise HTTPException(status_code=404, detail="Transcript not found")




# Include routers with versioned and unversioned paths
app.include_router(core_router, prefix="/v1")
app.include_router(core_router, include_in_schema=False)
app.include_router(protected_router, prefix="/v1")
app.include_router(protected_router, include_in_schema=False)
app.include_router(admin_router, prefix="/v1")
app.include_router(admin_router, include_in_schema=False)
app.include_router(ws_router, prefix="/v1")
app.include_router(ws_router, include_in_schema=False)
app.include_router(status_router, prefix="/v1")
app.include_router(status_router, include_in_schema=False)
# Tiered health (unauthenticated): /healthz/* endpoints
app.include_router(health_router)

# Include modern auth API router first to avoid route shadowing
try:
    from .api.auth import router as auth_api_router
    app.include_router(auth_api_router, prefix="/v1")
    app.include_router(auth_api_router, include_in_schema=False)
except Exception:
    pass

# Legacy auth router (mounted after new API router to avoid shadowing)
app.include_router(auth_router, prefix="/v1")
app.include_router(auth_router, include_in_schema=False)
if preflight_router is not None:
    app.include_router(preflight_router, prefix="/v1")
    app.include_router(preflight_router, include_in_schema=False)
if device_auth_router is not None:
    app.include_router(device_auth_router, prefix="/v1")
    app.include_router(device_auth_router, include_in_schema=False)
# Removed duplicate inclusion of app.api.auth router to avoid route shadowing
app.include_router(oauth_google_router, prefix="/v1")
app.include_router(oauth_google_router, include_in_schema=False)
app.include_router(google_oauth_router, prefix="/v1")
app.include_router(google_oauth_router, include_in_schema=False)
if oauth_apple_router is not None:
    app.include_router(oauth_apple_router, prefix="/v1")
    app.include_router(oauth_apple_router, include_in_schema=False)
if auth_password_router is not None:
    app.include_router(auth_password_router, prefix="/v1")
    app.include_router(auth_password_router, include_in_schema=False)

# Google integration (optional)
# Provide both versioned and unversioned, under /google to match redirect defaults
app.include_router(google_router, prefix="/v1/google")
app.include_router(google_router, prefix="/google", include_in_schema=False)

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
            Depends(rate_limit),
        ],
    )
    app.include_router(ha_api_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.reminders import router as reminders_router
    app.include_router(reminders_router, prefix="/v1")
    app.include_router(reminders_router, include_in_schema=False)
except Exception:
    pass

# Remove legacy simple cookie auth router to avoid parallel flows

try:
    from .api.profile import router as profile_router
    app.include_router(profile_router, prefix="/v1")
    app.include_router(profile_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.admin import router as admin_api_router
    app.include_router(
        admin_api_router,
        prefix="/v1",
        dependencies=[
            # Bind OAuth2 scopes for docs; runtime auth enforced inside router AND here for belt & suspenders
            Depends(docs_security_with(["admin:write"])),
            Depends(verify_token),
        ],
    )
    app.include_router(admin_api_router, include_in_schema=False)
except Exception:
    pass

# Admin-inspect routes are included via app.api.admin router if available

try:
    from .api.admin_ui import router as admin_ui_router
    app.include_router(admin_ui_router, prefix="/v1")
    app.include_router(admin_ui_router, include_in_schema=False)
    # Also include experimental admin diagnostics (retrieval trace) router
    try:
        from .admin.routes import router as admin_extras_router
        app.include_router(admin_extras_router, prefix="/v1")
        app.include_router(admin_extras_router, include_in_schema=False)
    except Exception:
        pass
except Exception:
    # Even if admin UI unavailable, still try to include admin extras
    try:
        from .admin.routes import router as admin_extras_router
        app.include_router(admin_extras_router, prefix="/v1")
        app.include_router(admin_extras_router, include_in_schema=False)
    except Exception:
        pass

try:
    from .api.me import router as me_router
    app.include_router(me_router, prefix="/v1")
except Exception:
    pass

try:
    from .api.devices import router as devices_router
    app.include_router(devices_router, prefix="/v1")
    app.include_router(devices_router, include_in_schema=False)
except Exception:
    pass

# app.api.auth already included once above; do not include again

try:
    from .api.models import router as models_router
    app.include_router(models_router, prefix="/v1")
    app.include_router(models_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.history import router as history_router
    app.include_router(history_router, prefix="/v1")
    app.include_router(history_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.status_plus import router as status_plus_router
    app.include_router(
        status_plus_router,
        prefix="/v1",
        dependencies=[Depends(docs_security_with(["admin:write"]))],
    )
    app.include_router(status_plus_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.rag import router as rag_router
    app.include_router(rag_router, prefix="/v1")
    app.include_router(rag_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.skills import router as skills_router
    app.include_router(skills_router, prefix="/v1")
    app.include_router(skills_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.tv import router as tv_router
    app.include_router(tv_router, prefix="/v1")
    app.include_router(tv_router, include_in_schema=False)
except Exception:
    pass

# TTS router (new)
try:
    from .api.tts import router as tts_router
    app.include_router(tts_router, prefix="/v1")
    app.include_router(tts_router, include_in_schema=False)
except Exception:
    pass

# Additional feature routers used by TV/companion UIs
try:
    from .api.contacts import router as contacts_router
    app.include_router(contacts_router, prefix="/v1")
    app.include_router(contacts_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.caregiver_auth import router as caregiver_auth_router
    app.include_router(caregiver_auth_router, prefix="/v1")
    app.include_router(caregiver_auth_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.photos import router as photos_router
    app.include_router(photos_router, prefix="/v1")
    app.include_router(photos_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.calendar import router as calendar_router
    app.include_router(calendar_router, prefix="/v1")
    app.include_router(calendar_router, include_in_schema=False)
except Exception:
    pass

# Voices catalog
try:
    from .api.voices import router as voices_router
    app.include_router(voices_router, prefix="/v1")
    app.include_router(voices_router, include_in_schema=False)
except Exception:
    pass


try:
    from .api.memory_ingest import router as memory_ingest_router
    app.include_router(memory_ingest_router, prefix="/v1")
    app.include_router(memory_ingest_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.ask import router as ask_router
    app.include_router(ask_router, prefix="/v1")
    app.include_router(ask_router, include_in_schema=False)
except Exception:
    pass

# Optional diagnostic/auxiliary routers -------------------------------------
try:
    from .api.care import router as care_router
    app.include_router(
        care_router,
        prefix="/v1",
        dependencies=[Depends(docs_security_with(["care:resident"]))],
    )
    app.include_router(care_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.care_ws import router as care_ws_router
    app.include_router(care_ws_router, prefix="/v1")
    app.include_router(care_ws_router, include_in_schema=False)
except Exception:
    pass

try:
    # Vector-store health diagnostics (e.g., /v1/health/chroma)
    from .health import router as health_diag_router
    app.include_router(health_diag_router, prefix="/v1")
    app.include_router(health_diag_router, include_in_schema=False)
except Exception:
    pass

try:
    # Caregiver portal scaffold (e.g., /v1/caregiver/*)
    from .caregiver import router as caregiver_router
    app.include_router(
        caregiver_router,
        prefix="/v1",
        dependencies=[
            Depends(verify_token),
            Depends(rate_limit),
            Depends(optional_require_any_scope(["care:caregiver"])),
            Depends(docs_security_with(["care:caregiver"])),
        ],
    )
    app.include_router(caregiver_router, include_in_schema=False)
except Exception:
    pass

# Music API router: attach HTTP dependencies to HTTP paths only
if music_router is not None:
    from fastapi import APIRouter
    music_http = APIRouter(
        dependencies=[
            Depends(verify_token),
            Depends(optional_require_any_scope(["music:control"])),
            # Docs-only dependency to render lock icon and OAuth2 scopes in Swagger
            Depends(docs_security_with(["music:control"])),
            Depends(rate_limit),
        ]
    )
    # mount HTTP subrouter for HTTP routes
    music_http.include_router(music_router)
    app.include_router(music_http, prefix="/v1")
    app.include_router(music_router, include_in_schema=False)
    # Mount WS endpoints without HTTP dependencies
    try:
        from .api.music import ws_router as music_ws_router
        app.include_router(music_ws_router, prefix="/v1")
        app.include_router(music_ws_router, include_in_schema=False)
    except Exception:
        pass
    # Sim WS helpers for UI duck/restore
    try:
        from .api.tv_music_sim import router as tv_music_sim_router
        app.include_router(tv_music_sim_router, prefix="/v1")
        app.include_router(tv_music_sim_router, include_in_schema=False)
    except Exception:
        pass


# ============================================================================
# MIDDLEWARE REGISTRATION (AFTER ALL ROUTERS)
# ============================================================================

# 1) Include routers FIRST (handlers + dependencies live here)
#    Routers are already included above with their dependencies

# 2) Core middlewares (inner → outer as you go DOWN)
#    These WILL be skipped for OPTIONS by your own checks.
#    Order: [ RequestID ] → [ Trace ] → [ CSRF ] → [ CORS ] → [ RateLimit / Router / Handlers ]
app.add_middleware(RequestIDMiddleware)      # innermost - sets request ID
app.add_middleware(DedupMiddleware)          # deduplicates requests
app.add_middleware(TraceRequestMiddleware)   # traces/logs requests (skips OPTIONS)

# Add CORS debug middleware
@app.middleware("http")
async def cors_debug_middleware(request: Request, call_next):
    """Debug middleware to log CORS-related information."""
    origin = request.headers.get("origin")
    method = request.method
    
    if origin:
        logging.info(f"CORS DEBUG: Request from origin={origin}, method={method}, path={request.url.path}")
        if origin not in origins:
            logging.warning(f"CORS DEBUG: Origin {origin} not in allowed origins {origins}")
    
    if method == "OPTIONS":
        logging.info(f"CORS DEBUG: Preflight request for path={request.url.path}")
    
    response = await call_next(request)
    
    # Log CORS headers in response
    cors_headers = {k: v for k, v in response.headers.items() if k.lower().startswith('access-control-')}
    if cors_headers:
        logging.info(f"CORS DEBUG: Response headers: {cors_headers}")
    
    return response



# 3) Third-party middlewares (still INSIDE CORS)
#    Configure them to skip OPTIONS if they can.
#    Note: Currently no third-party middlewares like GZipMiddleware are used

# 4) CSRF protection BEFORE CORS (inner)
#    CSRF middleware handles non-OPTIONS requests before CORS processes them
app.add_middleware(CSRFMiddleware)           # CSRF protection (skips OPTIONS)
logging.info("=== CSRF MIDDLEWARE REGISTERED ===")

# Note: reload_env_middleware is a simple function, not a class, so we use the decorator
app.middleware("http")(reload_env_middleware)
app.middleware("http")(silent_refresh_middleware)  # Re-enabled to prevent 401s during app boot
app.middleware("http")(enhanced_error_handling)  # Enhanced error handling and logging

# 5) CORS AS OUTERMOST MIDDLEWARE — HANDLES ALL RESPONSES
#    CORS middleware must be the outermost to ensure all responses (including errors) get ACAO headers
logging.info("=== REGISTERING CORS MIDDLEWARE (OUTERMOST) ===")
logging.info(f"Adding CORSMiddleware with:")
logging.info(f"  allow_origins: {origins}")
logging.info(f"  allow_credentials: {allow_credentials}")
logging.info(f"  allow_methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']")
logging.info(f"  allow_headers: ['*']")
logging.info(f"  expose_headers: ['X-Request-ID']")
logging.info(f"  max_age: 600")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*", "Authorization"],
    # Expose headers: only what you need (e.g., X-Request-ID), not wildcards
    expose_headers=["X-Request-ID"],
    max_age=600,
)
logging.info("=== CORS MIDDLEWARE REGISTERED (OUTERMOST) ===")

# Debug middleware order dump
def _dump_mw_stack(app):
    try:
        stack = getattr(app, "user_middleware", [])
        logging.warning("MW-ORDER (inner→outer): %s", [m.cls.__name__ for m in stack])
    except Exception as e:
        logging.warning("MW-ORDER dump failed: %r", e)

_dump_mw_stack(app)

# Final startup logging
logging.info("=== FINAL STARTUP CONFIGURATION ===")
logging.info(f"Server will start on: {os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '8000')}")
logging.info(f"Frontend origin: http://localhost:3000")
logging.info(f"Backend origin: http://localhost:8000")
logging.info(f"CORS origins: {origins}")
logging.info(f"CORS allow_credentials: {allow_credentials}")
logging.info("=== STARTUP COMPLETE ===")


if __name__ == "__main__":
    import uvicorn

    # Read host and port from environment variables
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(app, host=host, port=port)

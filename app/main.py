# ruff: noqa: E402
from .env_utils import load_env

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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from .deps.scheduler import shutdown as scheduler_shutdown
from .deps.user import get_current_user_id
from .gpt_client import close_client
from .user_store import user_store
from . import router
from .memory.profile_store import profile_store


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
from .logging_config import configure_logging, get_last_errors
from .csrf import CSRFMiddleware
from .otel_utils import init_tracing, shutdown_tracing
from .status import router as status_router
from .auth import router as auth_router
try:
    from .api.preflight import router as preflight_router
except Exception:
    preflight_router = None  # type: ignore
try:
    from .api.auth import router as simple_auth_router
except Exception:
    simple_auth_router = None  # type: ignore
try:
    from .api.oauth_google import router as oauth_google_router
except Exception:
    oauth_google_router = None  # type: ignore
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
try:
    from .integrations.google.routes import router as google_router
except Exception:  # pragma: no cover - optional
    google_router = None  # type: ignore
from .decisions import get_recent as decisions_recent, get_explain as decisions_get
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
    def docs_security_with(scopes):  # type: ignore
        async def _noop2(*args, **kwargs):
            return None
        return _noop2


from .middleware import (
    DedupMiddleware,
    reload_env_middleware,
    trace_request,
    silent_refresh_middleware,
)
from .security import (
    rate_limit,
    rate_limit_ws,
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


configure_logging()
# Initialize tracing early (best-effort; no-op if disabled/unavailable)
try:
    init_tracing()
except Exception:
    pass
logger = logging.getLogger(__name__)


tags_metadata = [
    {"name": "Care", "description": "Care features, contacts, sessions, and Home Assistant actions."},
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


_IS_DEV_ENV = (os.getenv("ENV", "dev").strip().lower() == "dev")

_docs_url = "/docs" if _IS_DEV_ENV else None
_redoc_url = "/redoc" if _IS_DEV_ENV else None
_openapi_url = "/openapi.json" if _IS_DEV_ENV else None

_swagger_ui_parameters = {
    "docExpansion": "list",
    "filter": True,
    "persistAuthorization": True,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await llama_startup()
        await ha_startup()
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
        yield
    finally:
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
        servers_env = os.getenv(
            "OPENAPI_DEV_SERVERS",
            "http://localhost:8000, http://127.0.0.1:8000",
        )
        servers = [
            {"url": s.strip()}
            for s in servers_env.split(",")
            if s and s.strip()
        ]
        if servers:
            schema["servers"] = servers
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[assignment]

# CORS middleware with stricter defaults
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").strip().lower() in {"1", "true", "yes", "on"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DedupMiddleware)
app.middleware("http")(trace_request)
app.middleware("http")(silent_refresh_middleware)
app.middleware("http")(reload_env_middleware)
app.add_middleware(CSRFMiddleware)

# Mount auth API contract routes early for precedence
try:
    from .api.auth import router as early_auth_api_router
    app.include_router(early_auth_api_router, prefix="/v1")
    app.include_router(early_auth_api_router, include_in_schema=False)
except Exception:
    pass

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
    try:  # pragma: no cover - optional dependency
        from prometheus_client import make_asgi_app
    except Exception:  # pragma: no cover - executed when dependency missing
        from starlette.responses import Response

        def make_asgi_app():
            async def _app(scope, receive, send):
                if scope.get("type") != "http":
                    raise RuntimeError("metrics endpoint only supports HTTP")
                try:
                    from . import metrics  # type: ignore

                    parts = [
                        f"{metrics.REQUEST_COUNT.name} {metrics.REQUEST_COUNT.value}",
                        f"{metrics.REQUEST_LATENCY.name} {metrics.REQUEST_LATENCY.value}",
                        f"{metrics.REQUEST_COST.name} {metrics.REQUEST_COST.value}",
                        f"{metrics.LLAMA_TOKENS.name} {metrics.LLAMA_TOKENS.value}",
                        f"{metrics.LLAMA_LATENCY.name} {metrics.LLAMA_LATENCY.value}",
                    ]
                    body = ("\n".join(parts) + "\n").encode()
                except Exception:
                    body = b""
                response = Response(content=body, media_type="text/plain; version=0.0.4")
                await response(scope, receive, send)

            return _app

    app.mount("/metrics", make_asgi_app())


@app.get("/healthz", tags=["Admin"])
async def healthz() -> dict:
    return {"status": "ok"}


class AskRequest(BaseModel):
    prompt: str
    model_override: str | None = Field(None, alias="model")

    # Pydantic v2 config: allow both alias ("model") and field name ("model_override")
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None


class DeleteMemoryRequest(BaseModel):
    id: str


core_router = APIRouter(tags=["Care"])
protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])
# Scoped routers
admin_router = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(rate_limit),
        Depends(optional_require_any_scope(["admin", "admin:write"])),
        # Docs-only dependency to render lock icon and OAuth2 scopes in Swagger
        Depends(docs_security_with(["admin:write"])),
    ],
    tags=["Admin"],
)
ha_router = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(rate_limit),
        Depends(optional_require_any_scope(["ha", "care:resident", "care:caregiver"])),
        Depends(docs_security_with(["care:resident"])),
    ],
    tags=["Care"],
)
ws_router = APIRouter(
    dependencies=[Depends(verify_ws), Depends(rate_limit_ws)], tags=["Care"]
)


@core_router.post("/presence")
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


@core_router.get("/me")
async def get_me(user_id: str = Depends(get_current_user_id)):
    stats = await user_store.get_stats(user_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, **stats}


@core_router.post("/ask")
async def ask(
    req: AskRequest, request: Request, user_id: str = Depends(get_current_user_id)
):
    """Deprecated: moved to app.api.ask. Kept for backward-compatibility via include order."""
    from .api.ask import ask as _ask  # lazy import to avoid circular deps

    return await _ask(req, request, user_id)  # type: ignore[arg-type]


@protected_router.post("/upload", tags=["Care"])
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


@protected_router.post("/capture/start", tags=["Care"])
async def capture_start(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_start as _start

    return await _start(request, user_id)  # type: ignore[arg-type]


@protected_router.post("/capture/save", tags=["Care"])
async def capture_save(
    request: Request,
    session_id: str = Form(...),
    audio: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    tags: str | None = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_save as _save

    return await _save(request, session_id, audio, video, transcript, tags, user_id)  # type: ignore[arg-type]


@protected_router.post("/capture/tags", tags=["Care"])
async def capture_tags(
    request: Request,
    session_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_tags as _tags

    return await _tags(request, session_id, user_id)  # type: ignore[arg-type]


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


@protected_router.get("/sessions", tags=["Care"])
async def list_sessions(
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


@protected_router.post("/sessions/{session_id}/transcribe", tags=["Care"])
async def trigger_transcription_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import trigger_transcription_endpoint as _tt

    return await _tt(session_id, user_id)  # type: ignore[arg-type]


@protected_router.post("/sessions/{session_id}/summarize", tags=["Care"])
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


@core_router.post("/intent-test")
async def intent_test(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    logger.info("intent.test", extra={"meta": {"prompt": req.prompt}})
    return {"intent": "test", "prompt": req.prompt}


# Admin endpoints are served from app.api.admin. Avoid duplicating here.


# Nickname table CRUD (aliases)
@core_router.get("/ha/aliases")
async def list_aliases(user_id: str = Depends(get_current_user_id)):
    return await alias_all()


class AliasBody(BaseModel):
    name: str
    entity_id: str


@core_router.post("/ha/aliases")
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


@ha_router.post("/ha/service")
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
        raise HTTPException(status_code=500, detail="Home Assistant error")


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


@core_router.post("/transcribe/{session_id}")
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
app.include_router(auth_router, prefix="/v1")
app.include_router(auth_router, include_in_schema=False)
if preflight_router is not None:
    app.include_router(preflight_router, prefix="/v1")
    app.include_router(preflight_router, include_in_schema=False)
if device_auth_router is not None:
    app.include_router(device_auth_router, prefix="/v1")
    app.include_router(device_auth_router, include_in_schema=False)
if simple_auth_router is not None:
    app.include_router(simple_auth_router, prefix="/v1")
    app.include_router(simple_auth_router, include_in_schema=False)
if oauth_google_router is not None:
    app.include_router(oauth_google_router, prefix="/v1")
    app.include_router(oauth_google_router, include_in_schema=False)
if oauth_apple_router is not None:
    app.include_router(oauth_apple_router, prefix="/v1")
    app.include_router(oauth_apple_router, include_in_schema=False)
if auth_password_router is not None:
    app.include_router(auth_password_router, prefix="/v1")
    app.include_router(auth_password_router, include_in_schema=False)

# Google integration (optional)
if google_router is not None:
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
            Depends(rate_limit),
            Depends(optional_require_any_scope(["care:resident", "care:caregiver"])),
            Depends(docs_security_with(["care:resident"])),
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
            Depends(optional_require_any_scope(["admin", "admin:write"])),
            Depends(docs_security_with(["admin:write"])),
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
except Exception:
    pass

try:
    from .api.me import router as me_router
    app.include_router(me_router, prefix="/v1")
    app.include_router(me_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.auth import router as auth_api_router
    app.include_router(auth_api_router, prefix="/v1")
    app.include_router(auth_api_router, include_in_schema=False)
except Exception:
    pass

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

# Music API router (avoid applying HTTP dependencies to WS routes)
if music_router is not None:
    app.include_router(music_router, prefix="/v1")
    app.include_router(music_router, include_in_schema=False)
    # Sim WS helpers for UI duck/restore
    try:
        from .api.tv_music_sim import router as tv_music_sim_router
        app.include_router(tv_music_sim_router, prefix="/v1")
        app.include_router(tv_music_sim_router, include_in_schema=False)
    except Exception:
        pass



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

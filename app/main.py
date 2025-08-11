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
from .status import router as status_router
from .auth import router as auth_router
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
    from .deps.scopes import require_scope, optional_require_scope
except Exception:  # pragma: no cover - optional

    def require_scope(scope: str):  # type: ignore
        async def _noop(*args, **kwargs):
            return None

        return _noop
    optional_require_scope = require_scope  # type: ignore


from .middleware import DedupMiddleware, reload_env_middleware, trace_request
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
logger = logging.getLogger(__name__)


tags_metadata = [
    {"name": "core", "description": "Core operations"},
    {
        "name": "sessions",
        "description": "Session capture and transcription",
    },
    {
        "name": "home-assistant",
        "description": "Home Assistant integration",
    },
    {"name": "status", "description": "System status"},
    {"name": "auth", "description": "Authentication"},
]


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


app = FastAPI(title="GesahniV2", lifespan=lifespan, openapi_tags=tags_metadata)

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
from .middleware import silent_refresh_middleware
app.middleware("http")(silent_refresh_middleware)
app.middleware("http")(reload_env_middleware)

# Optional static mount for TV shared photos
try:
    _tv_dir = os.getenv("TV_PHOTOS_DIR", "data/shared_photos")
    if _tv_dir:
        app.mount("/shared_photos", StaticFiles(directory=_tv_dir), name="shared_photos")
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


@app.get("/healthz", tags=["status"])
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


core_router = APIRouter(tags=["core"])
protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])
# Scoped routers
admin_router = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(rate_limit),
        Depends(optional_require_scope("admin")),
    ],
    tags=["admin"],
)
ha_router = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(rate_limit),
        Depends(optional_require_scope("ha")),
    ],
    tags=["home-assistant"],
)
ws_router = APIRouter(
    dependencies=[Depends(verify_ws), Depends(rate_limit_ws)], tags=["sessions"]
)


@core_router.post("/presence")
async def presence(present: bool = True, user_id: str = Depends(get_current_user_id)):
    _set_presence(user_id, bool(present))
    return {"status": "ok"}


@core_router.post("/ha/webhook")
async def ha_webhook(request: Request, user_id: str = Depends(get_current_user_id)):
    # Verify signature and dispatch event
    try:
        body = await verify_webhook(request)  # type: ignore[arg-type]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="bad_request")
    try:
        data = (
            json.loads(body.decode("utf-8"))
            if isinstance(body, (bytes, bytearray))
            else {}
        )
    except Exception:
        data = {}
    _on_ha_event(data if isinstance(data, dict) else {})
    return {"status": "ok"}


# Memory export/delete --------------------------------------------------------


@core_router.get("/memories/export")
async def export_memories(user_id: str = Depends(get_current_user_id)):
    out = {"profile": [], "episodic": []}
    try:
        # Episodic via vector store listing when available
        from .memory.api import _store as _vs  # type: ignore

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
        from .memory.api import _store as _vs  # type: ignore

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


@protected_router.post("/upload", tags=["sessions"])
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
    logger.info(f"File uploaded to {dest}")
    return {"session_id": session_id}


@protected_router.post("/capture/start", tags=["sessions"])
async def capture_start(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_start as _start

    return await _start(request, user_id)  # type: ignore[arg-type]


@protected_router.post("/capture/save", tags=["sessions"])
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


@protected_router.post("/capture/tags", tags=["sessions"])
async def capture_tags(
    request: Request,
    session_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_tags as _tags

    return await _tags(request, session_id, user_id)  # type: ignore[arg-type]


@protected_router.get("/capture/status/{session_id}", tags=["sessions"])
async def capture_status(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import capture_status as _status

    return await _status(session_id, user_id)  # type: ignore[arg-type]


@protected_router.get("/search/sessions", tags=["sessions"])
async def search_sessions(
    q: str,
    sort: str = "recent",
    page: int = 1,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import search_session_store as _search

    return await _search(q, sort=sort, page=page, limit=limit)  # type: ignore[arg-type]


@protected_router.get("/sessions", tags=["sessions"])
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


@protected_router.post("/sessions/{session_id}/transcribe", tags=["sessions"])
async def trigger_transcription_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    from .api.sessions import trigger_transcription_endpoint as _tt

    return await _tt(session_id, user_id)  # type: ignore[arg-type]


@protected_router.post("/sessions/{session_id}/summarize", tags=["sessions"])
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
    logger.info("Intent test for: %s", req.prompt)
    return {"intent": "test", "prompt": req.prompt}


# Router decisions admin + explain endpoints
@core_router.get("/explain")
async def explain_route(req_id: str, user_id: str = Depends(get_current_user_id)):
    data = decisions_get(req_id)
    if not data:
        raise HTTPException(status_code=404, detail="not_found")
    return data


@core_router.get("/admin/router/decisions")
async def list_router_decisions(
    limit: int = Query(default=500, ge=1, le=1000), user_id: str = Depends(get_current_user_id)
):
    return {"items": decisions_recent(limit)}


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


# Profile and Onboarding endpoints ---------------------------------------------


class UserProfile(BaseModel):
    name: str | None = None
    email: str | None = None
    timezone: str | None = None
    language: str | None = None
    communication_style: str | None = None  # "casual", "formal", "technical"
    interests: list[str] | None = None
    occupation: str | None = None
    home_location: str | None = None
    preferred_model: str | None = None  # "gpt-4o", "llama3", "auto"
    notification_preferences: dict | None = None
    calendar_integration: bool = False
    gmail_integration: bool = False
    onboarding_completed: bool = False
    # Accessibility and voice preferences (Stage 1 onboarding)
    speech_rate: float | None = None          # 0.8..1.2 (1.0 = normal)
    input_mode: str | None = None             # "voice" | "touch" | "both"
    font_scale: float | None = None           # 0.9..1.4
    wake_word_enabled: bool = False


class OnboardingStep(BaseModel):
    step: str
    completed: bool
    data: dict | None = None


@core_router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Get user profile and preferences"""
    profile = profile_store.get(user_id)
    return UserProfile(**profile)


@core_router.post("/profile")
async def update_profile(
    profile: UserProfile, 
    user_id: str = Depends(get_current_user_id)
):
    """Update user profile and preferences"""
    profile_data = profile.model_dump(exclude_none=True)
    profile_store.update(user_id, profile_data)
    return {"status": "success", "message": "Profile updated successfully"}


@core_router.get("/onboarding/status")
async def get_onboarding_status(user_id: str = Depends(get_current_user_id)):
    """Get onboarding completion status"""
    profile = profile_store.get(user_id)
    steps = [
        {"step": "welcome", "completed": True, "data": None},
        {"step": "basic_info", "completed": bool(profile.get("name")), "data": {"name": profile.get("name")}},
        # Stage 1 immediate device preferences
        {
            "step": "device_prefs",
            "completed": bool(profile.get("speech_rate") and profile.get("font_scale")),
            "data": {
                "speech_rate": profile.get("speech_rate"),
                "input_mode": profile.get("input_mode"),
                "font_scale": profile.get("font_scale"),
                "wake_word_enabled": profile.get("wake_word_enabled"),
            },
        },
        {"step": "preferences", "completed": bool(profile.get("communication_style")), "data": {"communication_style": profile.get("communication_style")}},
        {"step": "integrations", "completed": bool(profile.get("calendar_integration") or profile.get("gmail_integration")), "data": {"calendar": profile.get("calendar_integration"), "gmail": profile.get("gmail_integration")}},
        {"step": "complete", "completed": profile.get("onboarding_completed", False), "data": None}
    ]
    return {
        "completed": profile.get("onboarding_completed", False),
        "steps": steps,
        "current_step": next((i for i, step in enumerate(steps) if not step["completed"]), len(steps) - 1)
    }


@core_router.post("/onboarding/complete")
async def complete_onboarding(user_id: str = Depends(get_current_user_id)):
    """Mark onboarding as completed"""
    profile_store.set(user_id, "onboarding_completed", True)
    return {"status": "success", "message": "Onboarding completed!"}


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


# Admin dashboard -------------------------------------------------------------


@core_router.get("/admin/errors")
async def admin_errors(limit: int = 50, user_id: str = Depends(get_current_user_id)):
    return {"errors": get_last_errors(limit)}


@core_router.get("/admin/self_review")
async def admin_self_review(user_id: str = Depends(get_current_user_id)):
    try:
        res = _get_self_review()
        return res or {"status": "unavailable"}
    except Exception:
        return {"status": "unavailable"}


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
if device_auth_router is not None:
    app.include_router(device_auth_router, prefix="/v1")
    app.include_router(device_auth_router, include_in_schema=False)

# Google integration (optional)
if google_router is not None:
    # Provide both versioned and unversioned, under /google to match redirect defaults
    app.include_router(google_router, prefix="/v1/google")
    app.include_router(google_router, prefix="/google", include_in_schema=False)

# New modular routers for HA and profile/admin
try:
    from .api.ha import router as ha_api_router
    app.include_router(ha_api_router, prefix="/v1")
    app.include_router(ha_api_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.reminders import router as reminders_router
    app.include_router(reminders_router, prefix="/v1")
    app.include_router(reminders_router, include_in_schema=False)
except Exception:
    pass

try:
    # Mount dev/simple cookie auth only when explicitly enabled
    if os.getenv("DEV_SIMPLE_AUTH", "0").strip().lower() in {"1", "true", "yes", "on"}:
        from .api.auth import router as auth_router
        app.include_router(auth_router, prefix="/v1")
        app.include_router(auth_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.profile import router as profile_router
    app.include_router(profile_router, prefix="/v1")
    app.include_router(profile_router, include_in_schema=False)
except Exception:
    pass

try:
    from .api.admin import router as admin_api_router
    app.include_router(admin_api_router, prefix="/v1")
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
    app.include_router(status_plus_router, prefix="/v1")
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



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

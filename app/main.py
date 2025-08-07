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
    Request,
    UploadFile,
    WebSocket,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from .deps.scheduler import shutdown as scheduler_shutdown
from .deps.user import get_current_user_id
from .gpt_client import close_client
from .user_store import user_store
from . import router


async def route_prompt(*args, **kwargs):
    logger.info("⬇️ main.route_prompt args=%s kwargs=%s", args, kwargs)
    try:
        res = await router.route_prompt(*args, **kwargs)
        logger.info("⬆️ main.route_prompt got res=%s", res)
        return res
    except Exception as e:  # pragma: no cover - defensive
        logger.error("💥 main.route_prompt bubbled exception: %s", e)
        raise


import app.skills  # populate SKILLS
from .home_assistant import (
    call_service,
    get_states,
    resolve_entity,
    startup_check as ha_startup,
)
from .llama_integration import startup_check as llama_startup
from .logging_config import configure_logging
from .status import router as status_router
from .auth import router as auth_router
from .transcription import (
    TranscriptionStream,
    close_whisper_client,
    transcribe_file,
)
from .middleware import DedupMiddleware, reload_env_middleware, trace_request
from .session_manager import (
    SESSIONS_DIR,
    generate_tags as queue_tag_extraction,
    save_session as finalize_capture_session,
    search_sessions as search_session_store,
    start_session as start_capture_session,
    get_session_meta,
)
from .session_store import SessionStatus, list_sessions as list_session_store
from .tasks import enqueue_summary, enqueue_transcription
from .security import rate_limit, rate_limit_ws, verify_token, verify_ws


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

# CORS middleware
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DedupMiddleware)
app.middleware("http")(trace_request)
app.middleware("http")(reload_env_middleware)

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


core_router = APIRouter(tags=["core"])
protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])
ws_router = APIRouter(
    dependencies=[Depends(verify_ws), Depends(rate_limit_ws)], tags=["sessions"]
)


@core_router.get("/me")
async def get_me(user_id: str = Depends(get_current_user_id)):
    stats = await user_store.get_stats(user_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, **stats}


@core_router.post("/ask")
async def ask(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    logger.info("Received prompt: %s", req.prompt)

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    status_code: int | None = None

    streamed_any: bool = False

    async def _stream_cb(token: str) -> None:
        nonlocal streamed_any
        streamed_any = True
        await queue.put(token)

    async def _producer() -> None:
        nonlocal status_code
        try:
            params = inspect.signature(route_prompt).parameters
            if "stream_cb" in params:
                result = await route_prompt(
                    req.prompt, req.model_override, user_id, stream_cb=_stream_cb
                )
            else:  # Compatibility with tests that monkeypatch route_prompt
                result = await route_prompt(req.prompt, req.model_override, user_id)
            # If the backend didn't stream any tokens, emit the final result once
            if not streamed_any and isinstance(result, str) and result:
                await queue.put(result)
        except HTTPException as exc:
            status_code = exc.status_code
            await queue.put(f"[error:{exc.detail}]")
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("Error processing prompt: %s", e)
            await queue.put("[error]")
        finally:
            await queue.put(None)

    asyncio.create_task(_producer())

    first_chunk = await queue.get()

    async def _streamer():
        if first_chunk is not None:
            yield first_chunk
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(
        _streamer(), media_type="text/plain", status_code=status_code or 200
    )


@protected_router.post("/upload", tags=["sessions"])
async def upload(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
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
    return await start_capture_session()


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
    tags_list = json.loads(tags) if tags else None
    await finalize_capture_session(session_id, audio, video, transcript, tags_list)
    return get_session_meta(session_id)


@protected_router.post("/capture/tags", tags=["sessions"])
async def capture_tags(
    request: Request,
    session_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    await queue_tag_extraction(session_id)
    return {"status": "accepted"}


@protected_router.get("/capture/status/{session_id}", tags=["sessions"])
async def capture_status(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    meta = get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="session not found")
    return meta


@protected_router.get("/search/sessions", tags=["sessions"])
async def search_sessions(
    q: str,
    sort: str = "recent",
    page: int = 1,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
):
    return await search_session_store(q, sort=sort, page=page, limit=limit)


@protected_router.get("/sessions", tags=["sessions"])
async def list_sessions(
    status: SessionStatus | None = None,
    user_id: str = Depends(get_current_user_id),
):
    return list_session_store(status)


@protected_router.post("/sessions/{session_id}/transcribe", tags=["sessions"])
async def trigger_transcription_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    enqueue_transcription(session_id, user_id)
    return {"status": "accepted"}


@protected_router.post("/sessions/{session_id}/summarize", tags=["sessions"])
async def trigger_summary_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    enqueue_summary(session_id)
    return {"status": "accepted"}


@ws_router.websocket("/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
):
    stream = TranscriptionStream(ws, transcribe_file)
    await stream.process()


@core_router.post("/intent-test")
async def intent_test(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    logger.info("Intent test for: %s", req.prompt)
    return {"intent": "test", "prompt": req.prompt}


@protected_router.get("/ha/entities", tags=["home-assistant"])
async def ha_entities(user_id: str = Depends(get_current_user_id)):
    try:
        return await get_states()
    except Exception as e:
        logger.exception("HA states error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@protected_router.post("/ha/service", tags=["home-assistant"])
async def ha_service(req: ServiceRequest, user_id: str = Depends(get_current_user_id)):
    try:
        resp = await call_service(req.domain, req.service, req.data or {})
        return resp or {"status": "ok"}
    except Exception as e:
        logger.exception("HA service error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@protected_router.get("/ha/resolve", tags=["home-assistant"])
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
app.include_router(ws_router, prefix="/v1")
app.include_router(ws_router, include_in_schema=False)
app.include_router(status_router, prefix="/v1")
app.include_router(status_router, include_in_schema=False)
app.include_router(auth_router, prefix="/v1")
app.include_router(auth_router, include_in_schema=False)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

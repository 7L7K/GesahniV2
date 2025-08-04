# ruff: noqa: E402
from .env_utils import load_env

load_env()
import logging
import uuid
from pathlib import Path
import os
import time
import asyncio
import json
from hashlib import sha256
import sys

from fastapi import (
    FastAPI,
    HTTPException,
    File,
    UploadFile,
    BackgroundTasks,
    Response,
    WebSocket,
    WebSocketDisconnect,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import Depends, Request
from .deps.user import get_current_user_id

from . import router


async def route_prompt(*args, **kwargs):
    return await router.route_prompt(*args, **kwargs)


import app.skills  # populate SKILLS
from .home_assistant import (
    get_states,
    call_service,
    resolve_entity,
    startup_check as ha_startup,
)
from .llama_integration import startup_check as llama_startup
from .logging_config import configure_logging, req_id_var
from .telemetry import LogRecord, log_record_var, utc_now
from .status import router as status_router
from .transcription import transcribe_file
from .history import append_history
from .middleware import DedupMiddleware
from .session_manager import (
    start_session as start_capture_session,
    save_session as finalize_capture_session,
    generate_tags as queue_tag_extraction,
    search_sessions as search_session_store,
    SESSIONS_DIR,
)
from .session_manager import get_session_meta
from .session_store import list_sessions as list_session_store, SessionStatus
from .tasks import enqueue_transcription, enqueue_summary
from .security import verify_token, rate_limit, verify_ws, rate_limit_ws
from .analytics import record_latency, latency_p95

configure_logging()
logger = logging.getLogger(__name__)


def _anon_user_id(request: Request) -> str:
    """Return an anonymous user identifier from request details (auth header → IP → random)."""
    auth = request.headers.get("Authorization")
    if auth:
        return sha256(auth.encode("utf-8")).hexdigest()[:32]

    ip = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else None)
    if ip:
        return sha256(ip.encode("utf-8")).hexdigest()[:32]

    return uuid.uuid4().hex[:32]


app = FastAPI(title="GesahniV2")

# ─── CORS MIDDLEWARE ───────────────────────────────────────────────────────────────
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # includes OPTIONS
    allow_headers=["*"],  # includes Content-Type, Authorization, etc.
)
# ───────────────────────────────────────────────────────────────────────────────────
app.add_middleware(DedupMiddleware)

app.include_router(status_router)


@app.middleware("http")
async def trace_request(request, call_next):
    rec = LogRecord(req_id=str(uuid.uuid4()))
    token_req = req_id_var.set(rec.req_id)
    token_rec = log_record_var.set(rec)
    rec.session_id = request.headers.get("X-Session-ID")
    rec.user_id = _anon_user_id(request)
    rec.channel = request.headers.get("X-Channel")
    rec.received_at = utc_now().isoformat()
    rec.started_at = rec.received_at
    start_time = time.monotonic()
    response: Response | None = None

    try:
        response = await call_next(request)
        rec.status = "OK"
    except asyncio.TimeoutError:
        rec.status = "ERR_TIMEOUT"
        raise
    finally:
        # compute and record latency
        rec.latency_ms = int((time.monotonic() - start_time) * 1000)
        await record_latency(rec.latency_ms)
        rec.p95_latency_ms = latency_p95()

        # tag response header
        if isinstance(response, Response):
            response.headers["X-Request-ID"] = rec.req_id

        # persist history & reset context vars
        await append_history(rec)
        log_record_var.reset(token_rec)
        req_id_var.reset(token_req)

    return response


@app.middleware("http")
async def reload_env_middleware(request: Request, call_next):
    load_env()
    return await call_next(request)


@app.on_event("startup")
async def startup_event() -> None:
    try:
        await llama_startup()
        await ha_startup()
    except Exception as e:
        logger.error(f"Startup check failed: {e}")
        sys.exit(1)


class AskRequest(BaseModel):
    prompt: str
    model: str | None = None


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None


@app.post("/ask")
async def ask(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    logger.info("Received prompt: %s", req.prompt)
    try:
        answer = await route_prompt(req.prompt, req.model, user_id)
        return {"response": answer}
    except Exception as e:
        logger.exception("Error processing prompt: %s", e)
        raise HTTPException(status_code=500, detail="Error processing prompt")


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
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


# ---------------------------------------------------------------------------
#  Capture & Transcription endpoints
# ---------------------------------------------------------------------------


@app.post("/capture/start")
async def capture_start(
    request: Request,
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    return await start_capture_session()


@app.post("/capture/save")
async def capture_save(
    request: Request,
    session_id: str = Form(...),
    audio: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    tags: str | None = Form(None),
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    tags_list = json.loads(tags) if tags else None
    await finalize_capture_session(session_id, audio, video, transcript, tags_list)
    return get_session_meta(session_id)


@app.post("/capture/tags")
async def capture_tags(
    request: Request,
    session_id: str = Form(...),
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    await queue_tag_extraction(session_id)
    return {"status": "accepted"}


@app.get("/capture/status/{session_id}")
async def capture_status(
    session_id: str,
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    meta = get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="session not found")
    return meta


@app.get("/search/sessions")
async def search_sessions(
    q: str,
    sort: str = "recent",
    page: int = 1,
    limit: int = 10,
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    return await search_session_store(q, sort=sort, page=page, limit=limit)


@app.get("/sessions")
async def list_sessions(
    status: SessionStatus | None = None,
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    return list_session_store(status)


@app.post("/sessions/{session_id}/transcribe")
async def trigger_transcription_endpoint(
    session_id: str,
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    enqueue_transcription(session_id, user_id)
    return {"status": "accepted"}


@app.post("/sessions/{session_id}/summarize")
async def trigger_summary_endpoint(
    session_id: str,
    _: None = Depends(verify_token),
    __: None = Depends(rate_limit),
    user_id: str = Depends(get_current_user_id),
):
    enqueue_summary(session_id)
    return {"status": "accepted"}


@app.websocket("/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str      = Depends(get_current_user_id),
    _: None           = Depends(verify_ws),
    __: None          = Depends(rate_limit_ws),
):
    # Now we’re clean—accept and roll
    await ws.accept()
    msg = await ws.receive()

    if "text" in msg and msg["text"]:
        try:
            json.loads(msg["text"])
        except Exception:
            await ws.send_json({"error": "invalid metadata"})
            await ws.close()
            return
        msg = await ws.receive()
    elif "bytes" not in msg:
        await ws.send_json({"error": "no data received"})
        await ws.close()
        return

    session_id = uuid.uuid4().hex
    audio_path = Path(SESSIONS_DIR) / session_id / "stream.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    full_text = ""

    with open(audio_path, "ab") as fh:
        try:
            while True:
                if "text" in msg and msg["text"]:
                    if msg["text"] == "end":
                        break
                    msg = await ws.receive()
                    continue

                chunk = msg.get("bytes")
                if not chunk:
                    msg = await ws.receive()
                    continue

                fh.write(chunk)
                tmp = audio_path.with_suffix(".part")
                tmp.write_bytes(chunk)

                try:
                    text = await transcribe_file(str(tmp))
                    full_text += (" " if full_text else "") + text
                    await ws.send_json({"text": full_text, "session_id": session_id})
                except Exception as e:
                    await ws.send_json({"error": str(e)})
                finally:
                    if tmp.exists():
                        tmp.unlink()

                msg = await ws.receive()
        except WebSocketDisconnect:
            pass


@app.post("/intent-test")
async def intent_test(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    logger.info("Intent test for: %s", req.prompt)
    return {"intent": "test", "prompt": req.prompt}


@app.get("/ha/entities")
async def ha_entities(user_id: str = Depends(get_current_user_id)):
    try:
        return await get_states()
    except Exception as e:
        logger.exception("HA states error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@app.post("/ha/service")
async def ha_service(req: ServiceRequest, user_id: str = Depends(get_current_user_id)):
    try:
        resp = await call_service(req.domain, req.service, req.data or {})
        return resp or {"status": "ok"}
    except Exception as e:
        logger.exception("HA service error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@app.get("/ha/resolve")
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
    except Exception as e:
        logger.exception("Transcription failed: %s", e)


@app.post("/transcribe/{session_id}")
async def start_transcription(
    session_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    background_tasks.add_task(_background_transcribe, session_id)
    return {"status": "accepted"}


@app.get("/transcribe/{session_id}")
async def get_transcription(
    session_id: str, user_id: str = Depends(get_current_user_id)
):
    transcript_path = Path(SESSIONS_DIR) / session_id / "transcript.txt"
    if transcript_path.exists():
        return {"text": transcript_path.read_text(encoding="utf-8")}
    raise HTTPException(status_code=404, detail="Transcript not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

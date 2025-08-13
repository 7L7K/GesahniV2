from __future__ import annotations

import asyncio
import inspect
import logging
import os
from importlib import import_module

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from app.deps.user import get_current_user_id
from app.otel_utils import start_span, get_trace_id_hex
from app.policy import moderation_precheck


logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    prompt: str
    model_override: str | None = Field(None, alias="model")
    # Optional hint for small-ask preset (e.g., client detected simple profile question)
    small_ask: bool | None = None

    # Pydantic v2 config: allow both alias ("model") and field name ("model_override")
    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        json_schema_extra={
            "example": {
                "prompt": "Summarize today's schedule",
                "model": "gpt-4o-mini",
                "small_ask": True,
            }
        },
    )


from app.security import rate_limit, verify_token


router = APIRouter(tags=["Care"])  # dependency added per-route to allow env gate


# Enforce auth/rate-limit with env gates
def _require_auth_for_ask() -> bool:
    return os.getenv("REQUIRE_AUTH_FOR_ASK", "1").strip().lower() in {"1", "true", "yes", "on"}


@router.post("/ask", dependencies=[Depends(rate_limit)])
async def ask(
    req: AskRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    logger.info("ask.entry", extra={"meta": {"user_id": user_id, "model_override": req.model_override, "prompt_len": len(req.prompt or "")}})

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
            # Safety: block obviously destructive phrases locally; conversational scam cues are handled in router with a warning
            if not moderation_precheck(req.prompt, extra_phrases=[]):
                raise HTTPException(status_code=400, detail="blocked_by_policy")
            # If auth is required for /ask, enforce JWT now
            if _require_auth_for_ask():
                await verify_token(request)
                # rate_limit applied via route dependency; keep explicit header snapshot behavior
            # Lazily import to respect tests that monkeypatch app.main.route_prompt
            main_mod = import_module("app.main")
            route_prompt = getattr(main_mod, "route_prompt")
            params = inspect.signature(route_prompt).parameters
            if "stream_cb" in params:
                result = await route_prompt(
                    req.prompt, req.model_override, user_id, stream_cb=_stream_cb
                )
            else:  # Compatibility with tests that monkeypatch route_prompt
                result = await route_prompt(req.prompt, req.model_override, user_id)
            if streamed_any:
                logger.info("ask.success", extra={"meta": {"user_id": user_id, "streamed": True}})
            else:
                logger.info("ask.success", extra={"meta": {"user_id": user_id, "streamed": False}})
                # If the backend didn't stream any tokens, emit the final result once
                if isinstance(result, str) and result:
                    await queue.put(result)
            # If we are in local fallback, hint UI via cookie
            try:
                from app.llama_integration import LLAMA_HEALTHY as _LL_OK

                if not _LL_OK and not os.getenv("OPENAI_API_KEY"):
                    # First token will prompt cookie via middleware; nothing to do here
                    pass
            except Exception:
                pass
        except HTTPException as exc:
            logger.exception("ask HTTPException user_id=%s", user_id)
            status_code = exc.status_code
            await queue.put(f"[error:{exc.detail}]")
        except Exception as e:  # pragma: no cover - defensive
            # Ensure HTTP status reflects failure and propagate a useful error token
            logger.exception("ask error user_id=%s", user_id)
            status_code = 500
            # Include exception type to avoid empty messages like "Exception()"
            detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            await queue.put(f"[error:{detail}]")
        finally:
            await queue.put(None)

    # Producer task emits tokens into the queue without blocking response start
    # Root span for this request
    attrs = {
        "user_id": user_id,
        "ip": request.headers.get("X-Forwarded-For") or (request.client.host if request.client else ""),
        "route": "/v1/ask",
    }
    span_ctx = start_span("ask.request", attrs)
    producer_task = asyncio.create_task(_producer())

    first_chunk = await queue.get()

    async def _streamer():
        try:
            # If producer signalled end immediately (e.g. empty result), exit cleanly
            if first_chunk is None:
                return
            # Otherwise stream first chunk and continue until sentinel
            yield first_chunk
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        except asyncio.CancelledError:
            # Client disconnected; cancel producer and stop cleanly
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except Exception:
                    pass
            raise
        finally:
            # Ensure producer is cleaned up when stream finishes for any reason
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except Exception:
                    pass

    # Negotiate basic streaming transport: SSE if requested via Accept, else text/plain
    accept = request.headers.get("accept", "")
    media_type = (
        "text/event-stream"
        if (
            "text/event-stream" in accept
            or os.getenv("FORCE_SSE", "").lower() in {"1", "true", "yes"}
        )
        else "text/plain"
    )

    async def _sse_wrapper(gen):
        try:
            async for chunk in gen:
                # Minimal SSE framing
                yield f"data: {chunk}\n\n"
        except asyncio.CancelledError:
            # Propagate cancellation to underlying generator cleanup
            raise

    generator = _streamer()
    if media_type == "text/event-stream":
        generator = _sse_wrapper(generator)

    resp = StreamingResponse(
        generator, media_type=media_type, status_code=status_code or 200
    )
    # Expose trace id for correlation
    try:
        tid = get_trace_id_hex()
        if tid:
            resp.headers["X-Trace-ID"] = tid
    except Exception:
        pass
    # Close span when response finishes (best-effort for streaming)
    try:
        span = span_ctx.__enter__()  # type: ignore
        @resp.background
        async def _finish_span():  # type: ignore
            try:
                pass
            finally:
                try:
                    span_ctx.__exit__(None, None, None)  # type: ignore
                except Exception:
                    pass
    except Exception:
        try:
            span_ctx.__exit__(None, None, None)  # type: ignore
        except Exception:
            pass
    return resp



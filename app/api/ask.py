from __future__ import annotations

import asyncio
import inspect
import logging
import os
from datetime import UTC, datetime
from importlib import import_module

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.deps.user import get_current_user_id
from app.otel_utils import get_trace_id_hex, start_span
from app.policy import moderation_precheck
from app.router import OLLAMA_TIMEOUT_MS, OPENAI_TIMEOUT_MS
from app.telemetry import hash_user_id

from ..security import _jwt_decode

logger = logging.getLogger(__name__)


# Telemetry and logging utilities
def _get_or_generate_request_id(request: Request) -> str:
    """Get X-Request-ID from headers or generate a new one."""
    try:
        rid = request.headers.get("X-Request-ID")
        if rid and rid.strip():
            return rid.strip()
    except Exception:
        pass

    # Generate a new request ID
    return str(uuid.uuid4())[:8]


def _get_trace_id() -> str | None:
    """Get current trace ID for correlation."""
    try:
        return get_trace_id_hex()
    except Exception:
        return None


def _should_log_verbose() -> bool:
    """Check if verbose payload logging is enabled for local dev."""
    return os.getenv("DEBUG_VERBOSE_PAYLOADS", "0").strip() in {"1", "true", "yes", "on"}


def _redact_sensitive_data(data: dict) -> dict:
    """Redact sensitive data from logs unless verbose mode is enabled."""
    if _should_log_verbose():
        return data

    # Create a copy to avoid modifying the original
    redacted = data.copy()

    # Redact sensitive fields
    sensitive_fields = {"prompt", "text", "message", "query", "q"}
    for field in sensitive_fields:
        if field in redacted:
            redacted[field] = f"<redacted-{field}>"

    # Redact messages content if present
    if "messages" in redacted and isinstance(redacted["messages"], list):
        for msg in redacted["messages"]:
            if isinstance(msg, dict) and "content" in msg:
                msg["content"] = "<redacted-content>"

    # Redact original_messages if present
    if "original_messages" in redacted and isinstance(redacted["original_messages"], list):
        for msg in redacted["original_messages"]:
            if isinstance(msg, dict) and "content" in msg:
                msg["content"] = "<redacted-content>"

    return redacted


class Message(BaseModel):
    role: str = Field(..., description="Message role: system|user|assistant")
    content: str = Field(..., description="Message text content")

    model_config = ConfigDict(title="Message")


class AskRequest(BaseModel):
    prompt: str | list[Message] = Field(
        ..., description="Canonical prompt: text or messages[]"
    )
    model: str | None = Field(
        None, description="Preferred model id (e.g., gpt-4o, llama3)"
    )
    stream: bool | None = Field(
        False, description="Force SSE when true; otherwise negotiated via Accept"
    )

    # Allow legacy alias 'model_override' in docs compatibility
    model_override: str | None = Field(None, exclude=True)

    model_config = ConfigDict(
        title="AskRequest",
        json_schema_extra={
            "examples": {
                "text_prompt": {
                    "summary": "Simple text prompt",
                    "description": "Basic text input for simple queries",
                    "value": {
                        "prompt": "What is the capital of France?",
                        "model": "gpt-4o",
                        "stream": False
                    }
                },
                "chat_messages": {
                    "summary": "Chat format with messages",
                    "description": "Structured chat format preserving role information",
                    "value": {
                        "prompt": [
                            {"role": "system", "content": "You are a helpful geography tutor."},
                            {"role": "user", "content": "What is the capital of France?"},
                            {"role": "assistant", "content": "The capital of France is Paris."},
                            {"role": "user", "content": "What about Italy?"}
                        ],
                        "model": "llama3",
                        "stream": True
                    }
                },
                "streaming_text": {
                    "summary": "Streaming text response",
                    "description": "Text prompt with streaming response",
                    "value": {
                        "prompt": "Write a short poem about mountains",
                        "model": "gpt-4o",
                        "stream": True
                    }
                }
            }
        },
    )


from app.security import verify_token

router = APIRouter(tags=["Care"])  # dependency added per-route to allow env gate


# Telemetry and logging utilities
def _get_or_generate_request_id(request: Request) -> str:
    """Get X-Request-ID from headers or generate a new one."""
    try:
        rid = request.headers.get("X-Request-ID")
        if rid and rid.strip():
            return rid.strip()
    except Exception:
        pass

    # Generate a new request ID
    return str(uuid.uuid4())[:8]


def _get_trace_id() -> str | None:
    """Get current trace ID for correlation."""
    try:
        return get_trace_id_hex()
    except Exception:
        return None


def _should_log_verbose() -> bool:
    """Check if verbose payload logging is enabled for local dev."""
    return os.getenv("DEBUG_VERBOSE_PAYLOADS", "0").strip() in {"1", "true", "yes", "on"}


def _redact_sensitive_data(data: dict) -> dict:
    """Redact sensitive data from logs unless verbose mode is enabled."""
    if _should_log_verbose():
        return data

    # Create a copy to avoid modifying the original
    redacted = data.copy()

    # Redact sensitive fields
    sensitive_fields = {"prompt", "text", "message", "query", "q"}
    for field in sensitive_fields:
        if field in redacted:
            redacted[field] = f"<redacted-{field}>"

    # Redact messages content if present
    if "messages" in redacted and isinstance(redacted["messages"], list):
        for msg in redacted["messages"]:
            if isinstance(msg, dict) and "content" in msg:
                msg["content"] = "<redacted-content>"

    # Redact original_messages if present
    if "original_messages" in redacted and isinstance(redacted["original_messages"], list):
        for msg in redacted["original_messages"]:
            if isinstance(msg, dict) and "content" in msg:
                msg["content"] = "<redacted-content>"

    return redacted


# Standardized response envelope utilities
def _create_json_response(
    ok: bool,
    rid: str | None = None,
    trace_id: str | None = None,
    data: dict | None = None,
    error: dict | None = None
) -> dict:
    """Create a standardized JSON response envelope."""
    response = {"ok": ok}

    if rid:
        response["rid"] = rid
    if trace_id:
        response["trace_id"] = trace_id
    if data:
        response["data"] = data
    if error:
        response["error"] = error

    return response


def _create_error_response(
    machine_code: str,
    human_message: str,
    status_code: int | None = None,
    details: dict | None = None
) -> dict:
    """Create a standardized error response."""
    error = {
        "code": machine_code,
        "message": human_message,
        "type": _map_http_status_to_error_type(status_code) if status_code else "client_error"
    }

    if details:
        error["details"] = details

    return error


def _create_sse_event(event_type: str, data: dict) -> str:
    """Create a standardized SSE event."""
    import json
    return f"data: {json.dumps({'event': event_type, 'data': data})}\n\n"


def _heartbeat_generator(interval: int = 30):
    """Generate periodic heartbeat events for SSE connections."""
    import asyncio
    from datetime import datetime, UTC

    async def stream_heartbeats():
        while True:
            await asyncio.sleep(interval)
            yield _create_sse_event("heartbeat", {"ts": datetime.now(UTC).isoformat()})

    return stream_heartbeats()


def _map_http_status_to_error_type(status_code: int) -> str:
    """Map HTTP status codes to standardized error types."""
    if status_code == 401 or status_code == 403:
        return "auth_error"
    elif status_code == 429:
        return "rate_limited"
    elif 400 <= status_code < 500:
        return "client_error"
    elif 500 <= status_code < 600:
        return "downstream_error"
    else:
        return "unknown_error"


# Auth gate dependency
async def auth_gate(request: Request) -> str:
    """
    Consolidated authentication gate for all /ask endpoints.

    This dependency:
    - Honors REQUIRE_AUTH_FOR_ASK environment variable
    - Honors ASK_STRICT_BEARER environment variable
    - Sets request.state.user_id
    - Returns 401 when missing/invalid

    Returns the user_id for authenticated requests, "anon" for unauthenticated.
    """
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        request.state.user_id = "anon"
        return "anon"

    # Check if authentication is required
    require_auth = os.getenv("REQUIRE_AUTH_FOR_ASK", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not require_auth:
        # Auth not required, set anon user
        request.state.user_id = "anon"
        return "anon"

    # Authentication is required
    use_strict_bearer = os.getenv("ASK_STRICT_BEARER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if use_strict_bearer:
        # Strict bearer token validation
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise HTTPException(status_code=500, detail="missing_jwt_secret")

        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]

        if not token:
            logger.info(
                "auth.missing_bearer",
                extra={
                    "meta": {"path": getattr(getattr(request, "url", None), "path", "/")}
                },
            )
            raise HTTPException(status_code=401, detail="Unauthorized")

        try:
            payload = _jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
            request.state.jwt_payload = payload

            # Extract user_id from JWT payload
            user_id = payload.get("sub") or payload.get("user_id") or "anon"
            request.state.user_id = user_id
            return user_id

        except jwt.PyJWTError:
            logger.info(
                "auth.invalid_token",
                extra={
                    "meta": {"path": getattr(getattr(request, "url", None), "path", "/")}
                },
            )
            raise HTTPException(status_code=401, detail="Unauthorized")
    else:
        # Use the standard verify_token which handles cookie/header hybrid auth
        try:
            await verify_token(request)
            # Get the user_id that was set by verify_token
            user_id = getattr(request.state, "user_id", None)
            if user_id is None:
                user_id = get_current_user_id(request)
            request.state.user_id = user_id
            return user_id
        except Exception as e:
            logger.info(
                "auth.verify_token_failed",
                extra={
                    "meta": {
                        "path": getattr(getattr(request, "url", None), "path", "/"),
                        "error": str(e)
                    }
                },
            )
            raise HTTPException(status_code=401, detail="Unauthorized")

# Log auth dependency configuration at startup
logger.info("🔐 AUTH: /v1/ask using auth_dependency=get_current_user_id")


# Enforce auth/rate-limit with env gates
def _require_auth_for_ask() -> bool:
    return os.getenv("REQUIRE_AUTH_FOR_ASK", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _verify_bearer_strict(request: Request) -> None:
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        return
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    if not token:
        logger.info(
            "auth.missing_bearer",
            extra={
                "meta": {"path": getattr(getattr(request, "url", None), "path", "/")}
            },
        )
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = _jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
        request.state.jwt_payload = payload
    except jwt.PyJWTError:
        logger.info(
            "auth.invalid_token",
            extra={
                "meta": {"path": getattr(getattr(request, "url", None), "path", "/")}
            },
        )
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _require_auth_dep(request: Request) -> None:
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        return
    # When auth is required for ask, enforce strict token validation before rate limiting
    if _require_auth_for_ask():
        # Prefer cookie/header hybrid validator to support cookie-auth flows; allow strict bearer via env
        if os.getenv("ASK_STRICT_BEARER", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            await _verify_bearer_strict(request)
        else:
            await verify_token(request)


@router.post(
    "/ask",
    dependencies=[Depends(auth_gate)],
    responses={
        200: {
            "content": {
                "text/plain": {"schema": {"example": "hello world"}},
                "text/event-stream": {"schema": {"example": "data: hello\n\n"}},
                "application/json": {"schema": {"example": {"status": "ok"}}},
            }
        }
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/AskRequest"}
                }
            }
        }
    },
)
async def _ask(request: Request, body: dict | None):
    """Internal ask function that accepts resolved user_id parameter."""
    # Resolve user_id from request
    user_id = get_current_user_id(request)
    # Step 1: Log entry point and payload details
    logger.info(
        "🔍 ASK ENTRY: /v1/ask hit with payload=%s",
        body,
        extra={
            "meta": {
                "payload_keys": (
                    list(body.keys()) if body and isinstance(body, dict) else []
                ),
                "model_override": (
                    body.get("model") or body.get("model_override")
                    if body and isinstance(body, dict)
                    else None
                ),
            }
        },
    )

    # Content-Type guard: only accept JSON bodies
    try:
        ct = (
            request.headers.get("content-type")
            or request.headers.get("Content-Type")
            or ""
        ).lower()
    except Exception:
        ct = ""
    if "application/json" not in ct:
        raise HTTPException(status_code=415, detail="unsupported_media_type")

    # Use canonical user_id from resolved parameter
    _user_hash = hash_user_id(user_id) if user_id != "anon" else "anon"

    # Enforce authentication - return 401 if no valid user
    if user_id == "anon":
        try:
            from ..metrics import ROUTER_ASK_USER_ID_MISSING_TOTAL

            ROUTER_ASK_USER_ID_MISSING_TOTAL.labels(
                env=os.getenv("ENV", "dev"), route="/v1/ask"
            ).inc()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Authentication required")

    # Liberal parsing: normalize various legacy shapes into (prompt_text, model, opts)
    def _dget(obj: dict | None, path: str):
        cur = obj or {}
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    def _normalize_payload(
        raw: dict | None,
    ) -> tuple[str, str | None, bool, bool, dict, str]:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=422, detail="invalid_request")

        # Detect payload shape
        shape = "text"  # default
        normalized_from = None

        # Check for chat format: prompt is a list of {role, content}
        if isinstance(raw.get("prompt"), list):
            shape = "chat"
            normalized_from = "prompt_list"
        # Check for nested format: input.prompt or input.text
        elif raw.get("input") and isinstance(raw.get("input"), dict):
            shape = "nested"
            normalized_from = "input_nested"
        # Check for other chat-like formats
        elif raw.get("messages") and isinstance(raw.get("messages"), list):
            shape = "chat"
            normalized_from = "messages_list"

        model = raw.get("model") or raw.get("model_override")
        stream_present = "stream" in raw
        stream_flag = bool(raw.get("stream", False))
        # Accept canonical keys and aliases
        prompt_val = raw.get("prompt")
        if isinstance(prompt_val, dict):
            # Some clients send { prompt: { text: "..." } }
            prompt_val = prompt_val.get("text") or prompt_val.get("content")
        if prompt_val is None:
            for key in ("message", "text", "query", "q"):
                if isinstance(raw.get(key), str):
                    prompt_val = raw.get(key)
                    break
        if prompt_val is None:
            inner = raw.get("input") if isinstance(raw.get("input"), dict) else None
            if inner:
                for key in ("prompt", "text", "message"):
                    if isinstance(inner.get(key), str):
                        prompt_val = inner.get(key)
                        break
                if prompt_val is None and isinstance(inner.get("messages"), list):
                    prompt_val = inner.get("messages")
        # messages[] path
        messages = raw.get("messages")
        if prompt_val is None and isinstance(messages, list):
            prompt_val = messages
        # dotted path input.prompt
        if prompt_val is None:
            dotted = _dget(raw, "input.prompt") or _dget(raw, "input.text")
            if isinstance(dotted, str):
                prompt_val = dotted
        # Normalize to text
        prompt_text: str | None = None
        if isinstance(prompt_val, str):
            prompt_text = prompt_val
        elif isinstance(prompt_val, list):
            try:
                parts = []
                for m in prompt_val:
                    if isinstance(m, dict):
                        c = str(m.get("content") or "").strip()
                        if c:
                            parts.append(c)
                prompt_text = "\n".join(parts).strip()
            except Exception:
                prompt_text = None
        if (
            not prompt_text
            or not isinstance(prompt_text, str)
            or not prompt_text.strip()
        ):
            raise HTTPException(status_code=422, detail="empty_prompt")
        # Forward select generation options when present
        gen_opts = {}
        for k in ("temperature", "top_p", "max_tokens"):
            if k in raw:
                gen_opts[k] = raw[k]
        return (
            prompt_text,
            (str(model).strip() if isinstance(model, str) and model.strip() else None),
            stream_flag,
            bool(stream_present),
            gen_opts,
            shape,
            normalized_from,
        )

    (
        prompt_text,
        model_override,
        stream_flag,
        stream_explicit,
        gen_opts,
        shape,
        normalized_from,
    ) = _normalize_payload(body)

    # Track shape normalization metrics
    if normalized_from:
        try:
            from ..metrics import ROUTER_SHAPE_NORMALIZED_TOTAL, normalize_shape_label

            normalized_from_shape = normalize_shape_label(normalized_from)
            normalized_to_shape = normalize_shape_label(shape)
            ROUTER_SHAPE_NORMALIZED_TOTAL.labels(
                from_shape=normalized_from_shape, to_shape=normalized_to_shape
            ).inc()
        except Exception:
            pass

    # Telemetry breadcrumb (once per request): include request id and stream flag
    try:
        rid = request.headers.get("X-Request-ID")
    except Exception:
        rid = None
    logger.info(
        "ask.entry",
        extra={
            "meta": {
                "user_hash": _user_hash,
                "model_override": model_override,
                "prompt_len": len(prompt_text or ""),
                "req_id": rid,
                "stream": bool(stream_flag),
            }
        },
    )

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    status_code: int | None = None
    _error_detail: str | dict | None = None
    _error_category: str | None = None

    streamed_any: bool = False

    async def _stream_cb(token: str) -> None:
        nonlocal streamed_any
        streamed_any = True
        await queue.put(token)

    async def _producer() -> None:
        nonlocal status_code
        try:
            # Safety: block obviously destructive phrases locally; conversational scam cues are handled in router with a warning
            if not moderation_precheck(prompt_text, extra_phrases=[]):
                try:
                    from app.metrics import VALIDATION_4XX_TOTAL  # type: ignore

                    VALIDATION_4XX_TOTAL.labels("/v1/ask", "400").inc()
                except Exception:
                    pass
                raise HTTPException(status_code=400, detail="blocked_by_policy")
            # Auth is enforced via route dependency to ensure verify_token runs before rate_limit
            # rate_limit applied via route dependency; keep explicit header snapshot behavior
            # Lazily import to respect tests that monkeypatch app.main.route_prompt
            main_mod = import_module("app.main")
            route_prompt = main_mod.route_prompt
            params = inspect.signature(route_prompt).parameters
            if "stream_cb" in params:
                result = await route_prompt(
                    prompt_text,
                    user_id,
                    model_override=model_override,
                    stream_cb=_stream_cb,
                    shape=shape,
                    normalized_from=normalized_from,
                    **gen_opts,
                )
            else:  # Compatibility with tests that monkeypatch route_prompt
                result = await route_prompt(
                    prompt_text, user_id, model_override=model_override, **gen_opts
                )
            if streamed_any:
                logger.info(
                    "ask.success",
                    extra={"meta": {"user_hash": _user_hash, "streamed": True}},
                )
            else:
                logger.info(
                    "ask.success",
                    extra={"meta": {"user_hash": _user_hash, "streamed": False}},
                )
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
            # Map provider/client errors to stable categories for consumers
            status_code = int(getattr(exc, "status_code", 400) or 400)
            code = "client_error"
            if status_code in (401, 403):
                code = "auth_error"
            elif status_code == 429:
                code = "rate_limited"
            elif status_code >= 500:
                code = "downstream_error"
            _error_category = code
            try:
                d = getattr(exc, "detail", None)
                if d is not None:
                    _error_detail = d
            except Exception:
                _error_detail = None
            # TEMP: Return detailed error info for debugging
            import traceback

            detailed_error = f"{code}: {detail}\n{traceback.format_exc()}"
            await queue.put(f"[error:{code}: {detailed_error}]")
        except Exception as e:  # pragma: no cover - defensive
            # Ensure HTTP status reflects failure and propagate a useful error token
            logger.exception("ask.error")
            status_code = 500
            # Include exception type to avoid empty messages like "Exception()"
            detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            _error_detail = detail
            _error_category = "downstream_error"
            # TEMP: Return detailed error info for debugging
            import traceback

            detailed_error = f"{detail}\n{traceback.format_exc()}"
            await queue.put(f"[error:downstream_error: {detailed_error}]")
        finally:
            await queue.put(None)

    # Producer task emits tokens into the queue without blocking response start
    # Root span for this request
    attrs = {
        "user_id": user_id,
        "ip": request.headers.get("X-Forwarded-For")
        or (request.client.host if request.client else ""),
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

    # Negotiate basic streaming transport: SSE if requested via Accept/body, else JSON
    accept = request.headers.get("accept", "")
    wants_sse = bool(
        (stream_flag)
        or ((not stream_explicit) and ("text/event-stream" in accept))
        or (os.getenv("FORCE_SSE", "").lower() in {"1", "true", "yes"})
    )
    media_type = "text/event-stream" if wants_sse else "application/json"

    async def _sse_wrapper(gen):
        try:
            async for chunk in gen:
                # Minimal SSE framing
                yield f"data: {chunk}\n\n"
        except asyncio.CancelledError:
            # Propagate cancellation to underlying generator cleanup
            raise
        except Exception:
            # Ensure producer cleanup on error
            try:
                if not producer_task.done():
                    producer_task.cancel()
                    try:
                        await producer_task
                    except Exception:
                        pass
            except Exception:
                pass
            raise

    if media_type == "text/event-stream":
        generator = _sse_wrapper(_streamer())
        resp = StreamingResponse(
            generator, media_type=media_type, status_code=status_code or 200
        )
        # Explicit SSE headers per contract
        try:
            resp.headers.setdefault("Cache-Control", "no-cache")
            resp.headers.setdefault("Connection", "keep-alive")
        except Exception:
            pass
    else:
        # Aggregate full result and return JSON for non-streaming clients
        # Drain the queue starting from first_chunk
        chunks: list[str] = []
        if isinstance(first_chunk, str) and first_chunk:
            chunks.append(first_chunk)
        # Continue reading until sentinel
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            if isinstance(chunk, str) and chunk:
                chunks.append(chunk)
        text_result = "".join(chunks)
        if status_code and status_code >= 400:
            # Error path: propagate detail with proper status
            detail_payload = (
                _error_detail
                if (isinstance(_error_detail, dict) or isinstance(_error_detail, list))
                else {"detail": str(_error_detail or _error_category or "error")}
            )
            resp = JSONResponse(detail_payload, status_code=int(status_code))
        else:
            resp = JSONResponse({"response": text_result}, status_code=200)
    # Ensure request id is present for correlation in clients
    try:
        rid = request.headers.get("X-Request-ID")
        if rid:
            resp.headers.setdefault("X-Request-ID", rid)
    except Exception:
        pass
    # Expose trace id for correlation
    try:
        tid = get_trace_id_hex()
        if tid:
            resp.headers["X-Trace-ID"] = tid
    except Exception:
        pass
    # Close span when response finishes (best-effort for streaming)
    try:
        _ = span_ctx.__enter__()  # type: ignore

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


async def ask(
    request: Request,
    body: dict | None = Body(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Public ask endpoint that resolves dependencies and calls internal _ask function."""
    return await _ask(request, body)


@router.post(
    "/ask/dry-explain",
    response_model=dict,
    include_in_schema=False,
)
async def ask_dry_explain(
    request: Request,
    body: dict | None = Body(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Shadow routing endpoint that returns routing decision without making model calls."""
    # Step 1: Log entry point and payload details
    logger.info(
        "🔍 ASK DRY-EXPLAIN: /v1/ask/dry-explain hit with payload=%s",
        body,
        extra={
            "meta": {
                "payload_keys": (
                    list(body.keys()) if body and isinstance(body, dict) else []
                ),
                "model_override": (
                    body.get("model") or body.get("model_override")
                    if body and isinstance(body, dict)
                    else None
                ),
            }
        },
    )

    # Content-Type guard: only accept JSON bodies
    try:
        ct = (
            request.headers.get("content-type")
            or request.headers.get("Content-Type")
            or ""
        ).lower()
    except Exception:
        ct = ""
    if "application/json" not in ct:
        raise HTTPException(status_code=415, detail="unsupported_media_type")

    # Use canonical user_id from get_current_user_id dependency
    _user_hash = hash_user_id(user_id) if user_id != "anon" else "anon"

    # Enforce authentication - return 401 if no valid user
    if user_id == "anon":
        try:
            from ..metrics import ROUTER_ASK_USER_ID_MISSING_TOTAL

            ROUTER_ASK_USER_ID_MISSING_TOTAL.labels(
                env=os.getenv("ENV", "dev"), route="/v1/ask/dry-explain"
            ).inc()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Authentication required")

    # Use the same normalization logic
    (
        prompt_text,
        model_override,
        stream_flag,
        stream_explicit,
        gen_opts,
        shape,
        normalized_from,
    ) = _normalize_payload(body)

    # Track shape normalization metrics
    if normalized_from:
        try:
            from ..metrics import ROUTER_SHAPE_NORMALIZED_TOTAL, normalize_shape_label

            normalized_from_shape = normalize_shape_label(normalized_from)
            normalized_to_shape = normalize_shape_label(shape)
            ROUTER_SHAPE_NORMALIZED_TOTAL.labels(
                from_shape=normalized_from_shape, to_shape=normalized_to_shape
            ).inc()
        except Exception:
            pass

    # Generate request ID
    import uuid

    request_id = str(uuid.uuid4())[:8]

    # Get routing decision without making actual calls
    from ..intent import detect_intent
    from ..model_picker import pick_model
    from ..tokenizer import count_tokens

    # Detect intent and count tokens
    norm_prompt = prompt_text.lower().strip()
    intent, priority = detect_intent(prompt_text)
    tokens = count_tokens(prompt_text)

    # Determine routing decision
    if model_override:
        mv = model_override.strip()
        if mv.startswith("gpt"):
            chosen_vendor = "openai"
            chosen_model = mv
            picker_reason = "explicit_override"
        elif mv.startswith("llama"):
            chosen_vendor = "ollama"
            chosen_model = mv
            picker_reason = "explicit_override"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown model '{mv}'")
    else:
        engine, model_name, picker_reason, keyword_hit = pick_model(
            prompt_text, intent, tokens
        )
        chosen_vendor = "openai" if engine == "gpt" else "ollama"
        chosen_model = model_name

    # Check circuit breakers
    from ..llama_integration import llama_circuit_open
    from ..router import _user_circuit_open

    cb_global_open = llama_circuit_open
    cb_user_open = await _user_circuit_open(user_id) if user_id else False

    # Return the routing decision
    result = {
        "ts": datetime.now(UTC).isoformat(),
        "rid": request_id,
        "uid": user_id,
        "path": "/v1/ask/dry-explain",
        "shape": shape,
        "normalized_from": normalized_from,
        "override_in": model_override,
        "intent": intent,
        "tokens_est": tokens,
        "picker_reason": picker_reason,
        "chosen_vendor": chosen_vendor,
        "chosen_model": chosen_model,
        "dry_run": True,
        "cb_user_open": cb_user_open,
        "cb_global_open": cb_global_open,
        "allow_fallback": True,
        "stream": bool(stream_flag),
    }

    if "keyword_hit" in locals() and keyword_hit:
        result["keyword_hit"] = keyword_hit

    return result


@router.post(
    "/ask/stream",
    response_class=StreamingResponse,
    include_in_schema=False,
)
async def ask_stream(
    request: Request,
    body: dict | None = Body(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Streaming endpoint with Server-Sent Events (SSE) support."""
    # Step 1: Log entry point and payload details
    logger.info(
        "🔍 ASK STREAM: /v1/ask/stream hit with payload=%s",
        body,
        extra={
            "meta": {
                "payload_keys": (
                    list(body.keys()) if body and isinstance(body, dict) else []
                ),
                "model_override": (
                    body.get("model") or body.get("model_override")
                    if body and isinstance(body, dict)
                    else None
                ),
            }
        },
    )

    # Content-Type guard: only accept JSON bodies
    try:
        ct = (
            request.headers.get("content-type")
            or request.headers.get("Content-Type")
            or ""
        ).lower()
    except Exception:
        ct = ""
    if "application/json" not in ct:
        raise HTTPException(status_code=415, detail="unsupported_media_type")

    # Use canonical user_id from get_current_user_id dependency
    _user_hash = hash_user_id(user_id) if user_id != "anon" else "anon"

    # Enforce authentication - return 401 if no valid user
    if user_id == "anon":
        try:
            from ..metrics import ROUTER_ASK_USER_ID_MISSING_TOTAL

            ROUTER_ASK_USER_ID_MISSING_TOTAL.labels(
                env=os.getenv("ENV", "dev"), route="/v1/ask/stream"
            ).inc()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Authentication required")

    # Use the same normalization logic
    (
        prompt_text,
        model_override,
        stream_flag,
        stream_explicit,
        gen_opts,
        shape,
        normalized_from,
    ) = _normalize_payload(body)

    # Track shape normalization metrics
    if normalized_from:
        try:
            from ..metrics import ROUTER_SHAPE_NORMALIZED_TOTAL, normalize_shape_label

            normalized_from_shape = normalize_shape_label(normalized_from)
            normalized_to_shape = normalize_shape_label(shape)
            ROUTER_SHAPE_NORMALIZED_TOTAL.labels(
                from_shape=normalized_from_shape, to_shape=normalized_to_shape
            ).inc()
        except Exception:
            pass

    # Generate request ID
    request_id = str(uuid.uuid4())[:8]

    async def stream_generator():
        try:
            # Get routing decision first
            from ..intent import detect_intent
            from ..model_picker import pick_model
            from ..tokenizer import count_tokens

            # Detect intent and count tokens
            norm_prompt = prompt_text.lower().strip()
            intent, priority = detect_intent(prompt_text)
            tokens = count_tokens(prompt_text)

            # Determine routing decision
            if model_override:
                mv = model_override.strip()
                if mv.startswith("gpt"):
                    chosen_vendor = "openai"
                    chosen_model = mv
                    picker_reason = "explicit_override"
                elif mv.startswith("llama"):
                    chosen_vendor = "ollama"
                    chosen_model = mv
                    picker_reason = "explicit_override"
                else:
                    # Unknown model
                    yield f"event: error\ndata: {json.dumps({'rid': request_id, 'error': 'unknown_model', 'model': mv})}\n\n"
                    return
            else:
                engine, model_name, picker_reason, keyword_hit = pick_model(
                    prompt_text, intent, tokens
                )
                chosen_vendor = "openai" if engine == "gpt" else "ollama"
                chosen_model = model_name

            # Check circuit breakers
            from ..llama_integration import llama_circuit_open
            from ..router import _user_circuit_open

            cb_global_open = llama_circuit_open
            cb_user_open = await _user_circuit_open(user_id) if user_id else False

            # Emit route event
            route_data = {
                "ts": datetime.now(UTC).isoformat(),
                "rid": request_id,
                "uid": user_id,
                "path": "/v1/ask/stream",
                "shape": shape,
                "normalized_from": normalized_from,
                "override_in": model_override,
                "intent": intent,
                "tokens_est": tokens,
                "picker_reason": picker_reason,
                "chosen_vendor": chosen_vendor,
                "chosen_model": chosen_model,
                "dry_run": False,
                "cb_user_open": cb_user_open,
                "cb_global_open": cb_global_open,
                "allow_fallback": True,
                "stream": True,
            }

            if "keyword_hit" in locals() and keyword_hit:
                route_data["keyword_hit"] = keyword_hit

            yield f"event: route\ndata: {json.dumps(route_data)}\n\n"

            # Stream the actual response
            async def stream_callback(token: str):
                yield f"event: delta\ndata: {json.dumps({'content': token})}\n\n"

            # Call the appropriate vendor
            try:
                if chosen_vendor == "openai":
                    from ..gpt_client import ask_gpt

                    result = await ask_gpt(
                        prompt_text,
                        model=chosen_model,
                        timeout=OPENAI_TIMEOUT_MS / 1000,
                        stream_cb=stream_callback,
                        **gen_opts,
                    )
                elif chosen_vendor == "ollama":
                    from ..llama_integration import ask_llama

                    result = await ask_llama(
                        prompt_text,
                        model=chosen_model,
                        timeout=OLLAMA_TIMEOUT_MS / 1000,
                        stream_cb=stream_callback,
                        **gen_opts,
                    )
                else:
                    yield f"event: error\ndata: {json.dumps({'rid': request_id, 'vendor': chosen_vendor, 'error_class': 'unknown_vendor'})}\n\n"
                    return

                # Emit done event
                done_data = {
                    "rid": request_id,
                    "vendor": chosen_vendor,
                    "model": chosen_model,
                    "final_tokens": tokens,  # This would be actual completion tokens
                }
                yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

            except Exception as e:
                # Emit error event
                error_data = {
                    "rid": request_id,
                    "vendor": chosen_vendor,
                    "error_class": type(e).__name__,
                    "error": str(e),
                }
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

        except Exception as e:
            # Emit error event for any other errors
            error_data = {
                "rid": request_id,
                "error_class": type(e).__name__,
                "error": str(e),
            }
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-RID": request_id,
        },
    )


@router.get(
    "/ask/replay/{rid}",
    dependencies=[Depends(_require_auth_dep)],
    response_model=dict,
    include_in_schema=False,
)
async def ask_replay(
    rid: str,
    request: Request,
):
    """Replay endpoint for debugging stored golden traces."""
    # This is a placeholder implementation
    # In a real implementation, you would:
    # 1. Load the stored golden trace from a database/cache
    # 2. Replay against current vendor configs
    # 3. Return diff between then and now

    # For now, return a mock response
    return {
        "rid": rid,
        "status": "not_implemented",
        "message": "Replay functionality not yet implemented",
        "note": "This would load stored golden trace and replay against current configs",
    }

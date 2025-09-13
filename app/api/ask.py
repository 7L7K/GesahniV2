from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from importlib import import_module

import jwt
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth_core import csrf_validate
from app.auth_core import require_scope as require_scope_core
from app.deps.user import get_current_user_id, require_user
from app.errors import BackendUnavailableError
from app.otel_utils import get_trace_id_hex, start_span
from app.policy import moderation_precheck

# OPENAI/OLLAMA timeouts are provided by the legacy router module in some
# configurations. Import them lazily with safe fallbacks to avoid hard
# import-time coupling to `app.router` (which may be a lightweight package).
try:
    from app.router import OLLAMA_TIMEOUT_MS, OPENAI_TIMEOUT_MS
except Exception:
    OPENAI_TIMEOUT_MS = 6000
    OLLAMA_TIMEOUT_MS = 4500
from app.security import verify_token
from app.security.auth_contract import require_auth
from app.telemetry import hash_user_id

from ..security import jwt_decode

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
    return os.getenv("DEBUG_VERBOSE_PAYLOADS", "0").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
    if "original_messages" in redacted and isinstance(
        redacted["original_messages"], list
    ):
        for msg in redacted["original_messages"]:
            if isinstance(msg, dict) and "content" in msg:
                msg["content"] = "<redacted-content>"

    return redacted


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
    return os.getenv("DEBUG_VERBOSE_PAYLOADS", "0").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
    if "original_messages" in redacted and isinstance(
        redacted["original_messages"], list
    ):
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
    error: dict | None = None,
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
    details: dict | None = None,
) -> dict:
    """Create a standardized error response."""
    error = {
        "code": machine_code,
        "message": human_message,
        "type": (
            _map_http_status_to_error_type(status_code)
            if status_code
            else "client_error"
        ),
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
    from datetime import UTC, datetime

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


# Log auth dependency configuration at startup
logger.info(
    "🔐 AUTH: /v1/ask using get_current_user_id + require_user + scope(chat:write) + CSRF"
)


# Enforce auth/rate-limit with env gates
def _require_auth_for_ask() -> bool:
    return os.getenv("REQUIRE_AUTH_FOR_ASK", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _dget(obj: dict | None, path: str):
    """Helper function to get nested dictionary values by dot-separated path."""
    cur = obj or {}
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _normalize_payload(
    raw: dict | None,
) -> tuple[str, str | None, bool, bool, dict, str]:
    """Normalize various payload shapes into a consistent format."""
    if not isinstance(raw, dict):
        from app.error_envelope import raise_enveloped

        raise_enveloped("invalid_request", "Invalid request format", status=422)

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
    if not prompt_text or not isinstance(prompt_text, str) or not prompt_text.strip():
        raise_enveloped("empty_prompt", "Prompt cannot be empty", status=422)
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


async def _verify_bearer_strict(request: Request) -> None:
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        return
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # Treat as auth failure rather than server error to avoid 500s
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required", hint="missing JWT secret configuration"
        )
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
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )
    try:
        payload = jwt_decode(token, secret, algorithms=["HS256"])  # type: ignore[arg-type]
        request.state.jwt_payload = payload
    except jwt.PyJWTError:
        logger.info(
            "auth.invalid_token",
            extra={
                "meta": {"path": getattr(getattr(request, "url", None), "path", "/")}
            },
        )
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )


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
    dependencies=[
        Depends(require_user),  # 401 on missing/invalid auth (WWW-Authenticate: Bearer)
        Depends(
            require_scope_core("chat:write")
        ),  # 403 on missing scope with structured detail
        Depends(csrf_validate),  # Enforce CSRF for POST when enabled
    ],
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
    # Enforce auth parity even in DRY_RUN mode
    require_auth(request)
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
        raise_enveloped(
            "unsupported_media_type", "Unsupported content type", status=415
        )

    # Use canonical user_id from resolved parameter
    _user_hash = hash_user_id(user_id) if user_id != "anon" else "anon"

    # Authentication and scope are enforced by dependencies above.

    # Liberal parsing: normalize various legacy shapes into (prompt_text, model, opts)

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
                from app.error_envelope import raise_enveloped

                raise_enveloped(
                    "content_policy", "Content blocked by policy", status=400
                )
            # Auth is enforced via route dependency to ensure verify_token runs before rate_limit
            # rate_limit applied via route dependency; keep explicit header snapshot behavior
            # Lazily import to respect tests that monkeypatch app.main.route_prompt
            try:
                # Prefer injected prompt router (DI via Depends when called by FastAPI)
                prompt_router = (
                    kwargs.get("route_prompt")
                    if "route_prompt" in kwargs
                    else getattr(request.app.state, "prompt_router", None)
                )
            except Exception:
                prompt_router = None

            if prompt_router is not None and not isinstance(prompt_router, Depends):
                # Build a minimal payload for backend callables
                payload = {
                    "prompt": prompt_text,
                    "user_id": user_id,
                    "model_override": model_override,
                    "gen_opts": gen_opts,
                    "shape": shape,
                    "normalized_from": normalized_from,
                }
                # Instrument and protect the backend call with timeout/circuit
                from time import monotonic

                from app.metrics import (
                    PROMPT_ROUTER_CALLS_TOTAL,
                    PROMPT_ROUTER_FAILURES_TOTAL,
                )

                backend_label = os.getenv("PROMPT_BACKEND", "dryrun").lower()
                PROMPT_ROUTER_CALLS_TOTAL.labels(backend_label).inc()

                start = monotonic()
                try:
                    # Timeout fence: don't let backend block for more than 10s
                    import asyncio

                    result = await asyncio.wait_for(
                        prompt_router(payload), timeout=10.0
                    )
                except TimeoutError:
                    elapsed = monotonic() - start
                    PROMPT_ROUTER_FAILURES_TOTAL.labels(backend_label, "timeout").inc()
                    logger.error(
                        "Prompt backend timeout: backend=%s elapsed=%.3fs",
                        backend_label,
                        elapsed,
                        exc_info=True,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "BACKEND_TIMEOUT",
                            "message": "Prompt backend timed out",
                            "cause": "timeout",
                        },
                    )
                except BackendUnavailableError as e:
                    elapsed = monotonic() - start
                    PROMPT_ROUTER_FAILURES_TOTAL.labels(
                        backend_label, "unavailable"
                    ).inc()
                    logger.error(
                        "Prompt backend unavailable: backend=%s elapsed=%.3fs error=%s",
                        backend_label,
                        elapsed,
                        e,
                        exc_info=True,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "ROUTER_UNAVAILABLE",
                            "message": "Prompt backend not configured",
                            "cause": str(e),
                        },
                    )
                except Exception as e:
                    elapsed = monotonic() - start
                    PROMPT_ROUTER_FAILURES_TOTAL.labels(backend_label, "error").inc()
                    logger.exception(
                        "Prompt backend call failed: backend=%s elapsed=%.3fs",
                        backend_label,
                        elapsed,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "BACKEND_UNAVAILABLE",
                            "message": "Prompt backend call failed",
                            "cause": str(e),
                        },
                    )
            else:
                try:
                    # Prefer the lightweight router entrypoint to avoid importing heavy modules
                    entry_mod = import_module("app.router.entrypoint")
                    route_prompt = entry_mod.route_prompt
                    params = inspect.signature(route_prompt).parameters
                except (ImportError, AttributeError, RuntimeError) as e:
                    # Router import/wiring failed - return 503 Service Unavailable
                    logger.error("Router import/wiring failed: %s", e, exc_info=True)
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "ROUTER_UNAVAILABLE",
                            "message": "Router is unavailable",
                            "cause": str(e),
                        },
                    )
                try:
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
                            prompt_text,
                            user_id,
                            model_override=model_override,
                            **gen_opts,
                        )
                except RuntimeError as e:
                    # Router explicitly indicates it hasn't been configured; translate to 503
                    logger.error("Router not configured: %s", e, exc_info=True)
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "ROUTER_UNAVAILABLE",
                            "message": "Router not configured",
                            "cause": str(e),
                        },
                    )
                except Exception as e:
                    # Router call failed - return 503 Service Unavailable
                    logger.error("Router call failed: %s", e, exc_info=True)
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "BACKEND_UNAVAILABLE",
                            "message": "Router call failed",
                            "cause": str(e),
                        },
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

            # Persist chat messages after successful response generation
            try:
                # Reconstruct messages for persistence
                messages_to_save = []

                # Add user message
                if prompt_text:
                    messages_to_save.append({"role": "user", "content": prompt_text})

                # Add assistant response
                if isinstance(result, str) and result:
                    messages_to_save.append({"role": "assistant", "content": result})

                # Save to database if we have messages
                if messages_to_save:
                    try:
                        from app.db.chat_repo import save_messages
                        from app.db.core import get_async_db

                        # Get database session
                        async with get_async_db() as session:
                            await save_messages(
                                session, user_id, request_id, messages_to_save
                            )

                        logger.debug(
                            "Chat messages persisted",
                            extra={
                                "meta": {
                                    "rid": request_id,
                                    "message_count": len(messages_to_save),
                                }
                            },
                        )
                    except Exception as db_error:
                        # Don't fail the request if persistence fails, just log
                        logger.warning(
                            "Failed to persist chat messages",
                            extra={"meta": {"rid": request_id, "error": str(db_error)}},
                        )

            except Exception as persist_error:
                # Defensive: don't let persistence errors break the request
                logger.warning(
                    "Chat persistence error",
                    extra={"meta": {"error": str(persist_error)}},
                )
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

            try:
                detail_text = (
                    d
                    if isinstance(d, str)
                    else str(d.get("detail") if isinstance(d, dict) else d)
                )
            except Exception:
                detail_text = None
            detailed_error = f"{code}: {detail_text}\n{traceback.format_exc()}"
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
    require_auth(request)
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
        raise_enveloped(
            "unsupported_media_type", "Unsupported content type", status=415
        )

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
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )

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
            raise_enveloped("unknown_model", f"Unknown model '{mv}'", status=400)
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
    require_auth(request)
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
        raise_enveloped(
            "unsupported_media_type", "Unsupported content type", status=415
        )

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
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )

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
        import asyncio
        import time

        def sse(event_type: str, data: dict) -> str:
            return f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"

        try:
            # Get routing decision first
            from ..intent import detect_intent
            from ..model_picker import pick_model
            from ..tokenizer import count_tokens

            # Detect intent and count tokens
            intent, _priority = detect_intent(prompt_text)
            tokens = count_tokens(prompt_text)

            # Determine routing decision
            if model_override:
                mv = model_override.strip()
                if mv.startswith("gpt"):
                    chosen_vendor = "openai"
                    chosen_model = mv
                elif mv.startswith("llama"):
                    chosen_vendor = "ollama"
                    chosen_model = mv
                else:
                    yield sse(
                        "error",
                        {"rid": request_id, "code": "unknown_model", "model": mv},
                    )
                    return
            else:
                engine, model_name, _picker_reason, _keyword_hit = pick_model(
                    prompt_text, intent, tokens
                )
                chosen_vendor = "openai" if engine == "gpt" else "ollama"
                chosen_model = model_name

            # Helpers -----------------------------------------------------
            def _fallback_vendor(vendor: str) -> str:
                return "openai" if vendor == "ollama" else "ollama"

            def _fallback_model(vendor: str) -> str:
                return "gpt-4o" if vendor == "openai" else "llama3:latest"

            stall_ms = int(os.getenv("STREAM_STALL_MS", "15000") or 15000)
            stall_s = max(1.0, stall_ms / 1000.0)
            ping_interval_s = 8.0

            current_queue: asyncio.Queue[str] = asyncio.Queue()

            async def _run_vendor(vendor: str, model: str) -> dict:
                async def _cb(tok: str):
                    await current_queue.put(tok)

                if vendor == "openai":
                    from ..gpt_client import ask_gpt

                    return await ask_gpt(
                        prompt_text,
                        model=model,
                        timeout=OPENAI_TIMEOUT_MS / 1000,
                        stream_cb=_cb,
                        **gen_opts,
                    )
                elif vendor == "ollama":
                    from ..llama_integration import ask_llama

                    return await ask_llama(
                        prompt_text,
                        model=model,
                        timeout=OLLAMA_TIMEOUT_MS / 1000,
                        stream_cb=_cb,
                        **gen_opts,
                    )
                else:
                    raise RuntimeError(f"unknown_vendor:{vendor}")

            async def _start(vendor: str, model: str) -> asyncio.Task:
                return asyncio.create_task(_run_vendor(vendor, model))

            task = await _start(chosen_vendor, chosen_model)
            last_token_ts = time.monotonic()
            next_ping_ts = last_token_ts + ping_interval_s
            final_or_error_sent = False
            tried_fallback = False
            active_vendor = chosen_vendor
            active_model = chosen_model

            while True:
                # Drain tokens with short wait to interleave pings and stall detection
                try:
                    tok = await asyncio.wait_for(current_queue.get(), timeout=0.5)
                    last_token_ts = time.monotonic()
                    next_ping_ts = last_token_ts + ping_interval_s
                    yield sse("delta", {"content": tok})
                except TimeoutError:
                    pass

                now = time.monotonic()
                if now >= next_ping_ts and not final_or_error_sent:
                    yield sse("ping", {"ts": now})
                    next_ping_ts = now + ping_interval_s

                if task.done():
                    try:
                        result = task.result()
                    except Exception as e:
                        if tried_fallback:
                            yield sse(
                                "error",
                                {
                                    "rid": request_id,
                                    "code": "upstream_error",
                                    "error": str(e),
                                },
                            )
                            final_or_error_sent = True
                            break
                        # attempt fallback once on error
                        tried_fallback = True
                        active_vendor = _fallback_vendor(active_vendor)
                        active_model = _fallback_model(active_vendor)
                        current_queue = asyncio.Queue()
                        task = await _start(active_vendor, active_model)
                        last_token_ts = time.monotonic()
                        next_ping_ts = last_token_ts + ping_interval_s
                        continue

                    # Completed successfully
                    yield sse(
                        "final",
                        {
                            "rid": request_id,
                            "vendor": active_vendor,
                            "model": active_model,
                            "usage": result.get("usage", {}),
                        },
                    )
                    final_or_error_sent = True
                    break

                # Stall detection
                if (now - last_token_ts) >= stall_s and not tried_fallback:
                    # Cancel primary and switch to fallback
                    tried_fallback = True
                    try:
                        task.cancel()
                    except Exception:
                        pass
                    active_vendor = _fallback_vendor(active_vendor)
                    active_model = _fallback_model(active_vendor)
                    current_queue = asyncio.Queue()
                    task = await _start(active_vendor, active_model)
                    last_token_ts = time.monotonic()
                    next_ping_ts = last_token_ts + ping_interval_s
                elif (now - last_token_ts) >= stall_s and tried_fallback:
                    # Fallback also stalled/fails
                    try:
                        task.cancel()
                    except Exception:
                        pass
                    if not final_or_error_sent:
                        yield sse(
                            "error", {"rid": request_id, "code": "upstream_stall"}
                        )
                        final_or_error_sent = True
                    break

        except Exception as e:
            yield sse(
                "error", {"rid": request_id, "code": "internal_error", "error": str(e)}
            )

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-RID": request_id,
        },
    )

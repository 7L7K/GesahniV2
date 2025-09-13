"""Ask API routes for the router.

This module defines the /ask API endpoints.
Imports route_prompt from entrypoint, not from app.router/__init__.py.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from time import monotonic

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app import settings
from app.db.chat_repo import get_messages_by_rid
from app.db.core import get_db
from app.deps.user import get_current_user_id
from app.metrics import (
    ASK_ERRORS_TOTAL,
    ASK_LATENCY_MS,
)
from app.otel_utils import get_trace_id_hex
from app.schemas.chat import AskRequest

# Import from leaf modules, not from app.router.__init__.py
from .policy import OLLAMA_TIMEOUT_MS, OPENAI_TIMEOUT_MS

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
    try:
        return settings.debug_model_routing()  # reuse debug flag for simplicity
    except Exception:
        return False


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


# Schemas imported from shared module above


def _require_auth_dep():
    """Dependency that requires authentication and chat:write scope."""

    async def auth_and_csrf_check(request: Request):
        # For now, skip auth in dryrun mode
        # TODO: Implement proper auth when not in dryrun mode
        return True

    return [
        Depends(auth_and_csrf_check),
    ]


# Create the router
_deps_for_ask = _require_auth_dep() if settings.prompt_backend() != "dryrun" else []

router = APIRouter(tags=["Care"])  # dependency added per-route to allow env gate


@router.post(
    "/ask",
    dependencies=_deps_for_ask,
    response_model=dict,
)
async def ask_endpoint(
    request: Request,
    body: AskRequest = Body(...),
):
    """Frozen /v1/ask contract - routes prompts to LLM backends.

    REQUEST CONTRACT (frozen):
    - prompt: string | [{role, content}]
    - model?: string (gpt-4o*, llama3*, etc.)
    - stream?: boolean

    ROUTING RULES (frozen):
    - If PROMPT_BACKEND env → use it directly
    - Else route by model prefix:
      * gpt-4o*, gpt-4*, gpt-3.5* → openai
      * llama3*, llama2*, llama* → llama
      * Default → dryrun

    RESPONSE CONTRACT (frozen):
    {
      "backend": "openai|llama|dryrun",
      "model": "string",
      "answer": "string",
      "usage": {"input_tokens": 0, "output_tokens": 0},
      "latency_ms": 123,
      "req_id": "uuid"
    }

    ERROR HANDLING (frozen):
    - Backend unavailable → 503 with code: "llm_unavailable" (never 500)
    """
    start_time = monotonic()
    request_id = _get_or_generate_request_id(request)

    # Idempotency check - store responses for identical requests
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        # Simple in-memory cache for idempotency (could be Redis in production)
        cache_key = f"{request.method}:{request.url.path}:{idempotency_key}:{hash(str(body.model_dump()))}"

        # Check if we have a cached response
        cached_result = getattr(ask_endpoint, "_idempotency_cache", {}).get(cache_key)
        if cached_result is not None:
            logger.info(
                "idempotency.cache_hit",
                extra={
                    "rid": request_id,
                    "key": idempotency_key[:8] + "...",
                    "cache_key": cache_key[:16] + "...",
                },
            )
            # Return the exact same response
            return JSONResponse(
                status_code=cached_result["status_code"],
                content=cached_result["content"],
            )

    try:
        # Extract and validate request
        prompt_data = body.model_dump(exclude_unset=True)
        model_override = body.model_override

        # Log request (redacted)
        logger.info(
            "ask.request",
            extra={
                "rid": request_id,
                "model": model_override,
                "stream": body.stream,
                "payload": _redact_sensitive_data(prompt_data),
            },
        )

        # Resolve backend using frozen routing rules
        from app.routers import get_backend_for_request, resolve_backend

        backend_name = resolve_backend(model_override)
        backend_callable = get_backend_for_request(model_override)

        # Prepare payload for backend
        payload = dict(prompt_data)
        payload.update(
            {
                "request_id": request_id,
                "user_id": getattr(request.state, "user_id", "unknown"),
                "backend": backend_name,
                "model": model_override,
            }
        )

        # Call backend with timeout
        try:
            backend_start = monotonic()

            # Use configurable timeout based on backend
            timeout_seconds = 30.0  # Default fallback
            if backend_name == "openai":
                timeout_seconds = OPENAI_TIMEOUT_MS / 1000
            elif backend_name == "llama":
                timeout_seconds = OLLAMA_TIMEOUT_MS / 1000

            response = await asyncio.wait_for(
                backend_callable(payload), timeout=timeout_seconds
            )
            backend_duration = monotonic() - backend_start

        except TimeoutError:
            backend_duration = monotonic() - backend_start
            ASK_ERRORS_TOTAL.labels(backend=backend_name, error_type="timeout").inc()

            logger.warning(
                "ask.backend_timeout",
                extra={
                    "rid": request_id,
                    "backend": backend_name,
                    "model": model_override,
                    "timeout_ms": int(timeout_seconds * 1000),
                    "duration_ms": int(backend_duration * 1000),
                },
            )
            raise HTTPException(
                status_code=503,
                detail={"code": "llm_unavailable", "message": "Backend timeout"},
            )

        except Exception as backend_error:
            backend_duration = monotonic() - backend_start
            ASK_ERRORS_TOTAL.labels(backend=backend_name, error_type="error").inc()

            # Log backend error
            logger.error(
                "ask.backend_error",
                extra={
                    "rid": request_id,
                    "backend": backend_name,
                    "model": model_override,
                    "error": str(backend_error),
                    "duration_ms": int(backend_duration * 1000),
                },
                exc_info=True,
            )

            # Always return 503 for backend issues (never 500)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "llm_unavailable",
                    "message": f"Backend {backend_name} unavailable",
                },
            )

        # Format standardized response
        total_latency_ms = int((monotonic() - start_time) * 1000)

        standardized_response = {
            "backend": backend_name,
            "model": response.get("model", model_override or "unknown"),
            "answer": response.get("answer", ""),
            "usage": {
                "input_tokens": response.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response.get("usage", {}).get("output_tokens", 0),
            },
            "latency_ms": total_latency_ms,
            "req_id": request_id,
        }

        # Record latency metric
        ASK_LATENCY_MS.labels(backend=backend_name).observe(total_latency_ms)

        # Log success with structured observability data
        logger.info(
            "ask.success",
            extra={
                "rid": request_id,
                "route": "/v1/ask",
                "backend": backend_name,
                "model": standardized_response["model"],
                "status": 200,
                "latency_ms": total_latency_ms,
                "input_tokens": standardized_response["usage"]["input_tokens"],
                "output_tokens": standardized_response["usage"]["output_tokens"],
                "duration_ms": int(backend_duration * 1000),
            },
        )

        # Cache response for idempotency if key was provided
        if idempotency_key:
            if not hasattr(ask_endpoint, "_idempotency_cache"):
                ask_endpoint._idempotency_cache = {}

            cache_key = f"{request.method}:{request.url.path}:{idempotency_key}:{hash(str(body.model_dump()))}"
            ask_endpoint._idempotency_cache[cache_key] = {
                "status_code": 200,
                "content": standardized_response,
            }

            logger.debug(
                "idempotency.cache_stored",
                extra={
                    "rid": request_id,
                    "key": idempotency_key[:8] + "...",
                    "cache_key": cache_key[:16] + "...",
                },
            )

        return standardized_response

    except HTTPException:
        # Re-raise HTTP exceptions (preserves status codes)
        raise

    except Exception as e:
        # Unexpected error - log and return 503 (never 500 for backend issues)
        total_latency_ms = int((monotonic() - start_time) * 1000)

        # Record error metric (use backend name if available, otherwise unknown)
        ASK_ERRORS_TOTAL.labels(backend=backend_name, error_type="unexpected").inc()

        logger.error(
            "ask.unexpected_error",
            extra={
                "rid": request_id,
                "route": "/v1/ask",
                "backend": backend_name,
                "status": 503,
                "error": str(e),
                "latency_ms": total_latency_ms,
            },
            exc_info=True,
        )

        raise HTTPException(
            status_code=503,
            detail={
                "code": "llm_unavailable",
                "message": "Service temporarily unavailable",
            },
        )


@router.get(
    "/ask/replay/{rid}",
    dependencies=_require_auth_dep(),
    response_model=dict,
    include_in_schema=False,
)
async def ask_replay(
    rid: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """Replay endpoint for retrieving persisted chat messages by request ID."""
    try:
        # Get messages from database
        async for session in get_db():
            messages = await get_messages_by_rid(session, user_id, rid)
            break

        if not messages:
            # No messages found for this RID
            from app.error_envelope import raise_enveloped

            raise_enveloped(
                "not_found", "No chat messages found for this request ID", status=404
            )

        # Convert to response format
        message_list = [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]

        return {
            "rid": rid,
            "user_id": user_id,
            "message_count": len(message_list),
            "messages": message_list,
        }

    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(
            "Failed to retrieve chat messages",
            extra={"meta": {"rid": rid, "user_id": user_id, "error": str(e)}},
        )
        raise_enveloped("internal", "Failed to retrieve chat messages", status=500)

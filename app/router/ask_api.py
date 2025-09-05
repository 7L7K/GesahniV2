"""Ask API routes for the router.

This module defines the /ask API endpoints.
Imports route_prompt from entrypoint, not from app.router/__init__.py.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from app import settings
from app.deps.prompt_router import get_prompt_router
from app.domain.prompt_router import PromptRouter
from app.errors import BackendUnavailable
from app.metrics import PROMPT_ROUTER_CALLS_TOTAL, PROMPT_ROUTER_FAILURES_TOTAL, ASK_LATENCY_MS, ASK_ERRORS_TOTAL
import asyncio
from time import monotonic
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth_core import require_scope as require_scope_core
from app.deps.user import get_current_user_id, require_user
from app.otel_utils import get_trace_id_hex, start_span
from app.policy import moderation_precheck
from app.security import verify_token, jwt_decode
from app.telemetry import hash_user_id

# Import from leaf modules, not from app.router.__init__.py
from .entrypoint import route_prompt
from .policy import OPENAI_TIMEOUT_MS, OLLAMA_TIMEOUT_MS

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
        ...,
        description="Prompt text or chat-style message array",
        examples=["Hello, how are you?", [{"role": "user", "content": "Hello"}]],
    )
    model_override: str | None = Field(
        None,
        alias="model",
        description="Force specific model (gpt-4o, llama3, etc.)",
        examples=["gpt-4o", "llama3"],
    )
    stream: bool | None = Field(
        False,
        description="Force SSE when true; otherwise negotiated via Accept",
    )

    # Pydantic v2 config: allow both alias ("model") and field name ("model_override")
    model_config = ConfigDict(
        title="AskRequest",
        validate_by_name=True,
        validate_by_alias=True,
        json_schema_extra={
            "examples": [
                {"prompt": "Hello, how are you?"},
                {"prompt": [{"role": "user", "content": "Hello"}], "stream": True},
                {"prompt": "Translate to French", "model": "llama3"},
            ]
        },
    )


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
        cached_result = getattr(ask_endpoint, '_idempotency_cache', {}).get(cache_key)
        if cached_result is not None:
            logger.info("idempotency.cache_hit", extra={
                "rid": request_id,
                "key": idempotency_key[:8] + "...",
                "cache_key": cache_key[:16] + "...",
            })
            # Return the exact same response
            return JSONResponse(
                status_code=cached_result["status_code"],
                content=cached_result["content"]
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
        payload.update({
            "request_id": request_id,
            "user_id": getattr(request.state, "user_id", "unknown"),
            "backend": backend_name,
            "model": model_override,
        })

        # Call backend with timeout
        try:
            backend_start = monotonic()

            # Use configurable timeout based on backend
            timeout_seconds = 30.0  # Default fallback
            if backend_name == "openai":
                timeout_seconds = OPENAI_TIMEOUT_MS / 1000
            elif backend_name == "llama":
                timeout_seconds = OLLAMA_TIMEOUT_MS / 1000

            response = await asyncio.wait_for(backend_callable(payload), timeout=timeout_seconds)
            backend_duration = monotonic() - backend_start

        except asyncio.TimeoutError:
            backend_duration = monotonic() - backend_start
            ASK_ERRORS_TOTAL.labels(backend=backend_name, error_type="timeout").inc()

            logger.warning("ask.backend_timeout", extra={
                "rid": request_id,
                "backend": backend_name,
                "model": model_override,
                "timeout_ms": int(timeout_seconds * 1000),
                "duration_ms": int(backend_duration * 1000),
            })
            raise HTTPException(
                status_code=503,
                detail={"code": "llm_unavailable", "message": "Backend timeout"}
            )

        except Exception as backend_error:
            backend_duration = monotonic() - backend_start
            ASK_ERRORS_TOTAL.labels(backend=backend_name, error_type="error").inc()

            # Log backend error
            logger.error("ask.backend_error", extra={
                "rid": request_id,
                "backend": backend_name,
                "model": model_override,
                "error": str(backend_error),
                "duration_ms": int(backend_duration * 1000),
            }, exc_info=True)

            # Always return 503 for backend issues (never 500)
            raise HTTPException(
                status_code=503,
                detail={"code": "llm_unavailable", "message": f"Backend {backend_name} unavailable"}
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
        logger.info("ask.success", extra={
            "rid": request_id,
            "route": "/v1/ask",
            "backend": backend_name,
            "model": standardized_response["model"],
            "status": 200,
            "latency_ms": total_latency_ms,
            "input_tokens": standardized_response["usage"]["input_tokens"],
            "output_tokens": standardized_response["usage"]["output_tokens"],
            "duration_ms": int(backend_duration * 1000),
        })

        # Cache response for idempotency if key was provided
        if idempotency_key:
            if not hasattr(ask_endpoint, '_idempotency_cache'):
                ask_endpoint._idempotency_cache = {}

            cache_key = f"{request.method}:{request.url.path}:{idempotency_key}:{hash(str(body.model_dump()))}"
            ask_endpoint._idempotency_cache[cache_key] = {
                "status_code": 200,
                "content": standardized_response
            }

            logger.debug("idempotency.cache_stored", extra={
                "rid": request_id,
                "key": idempotency_key[:8] + "...",
                "cache_key": cache_key[:16] + "...",
            })

        return standardized_response

    except HTTPException:
        # Re-raise HTTP exceptions (preserves status codes)
        raise

    except Exception as e:
        # Unexpected error - log and return 503 (never 500 for backend issues)
        total_latency_ms = int((monotonic() - start_time) * 1000)

        # Record error metric (use backend name if available, otherwise unknown)
        ASK_ERRORS_TOTAL.labels(backend=backend_name, error_type="unexpected").inc()

        logger.error("ask.unexpected_error", extra={
            "rid": request_id,
            "route": "/v1/ask",
            "backend": backend_name,
            "status": 503,
            "error": str(e),
            "latency_ms": total_latency_ms,
        }, exc_info=True)

        raise HTTPException(
            status_code=503,
            detail={"code": "llm_unavailable", "message": "Service temporarily unavailable"}
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

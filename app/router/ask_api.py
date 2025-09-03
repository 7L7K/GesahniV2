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
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth_core import csrf_validate, require_scope as require_scope_core
from app.deps.user import get_current_user_id, require_user
from app.otel_utils import get_trace_id_hex, start_span
from app.policy import moderation_precheck
from app.security import jwt_decode, verify_token
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
    return [
        Depends(get_current_user_id),
        Depends(require_user),
        Depends(require_scope_core("chat:write")),
        Depends(csrf_validate),
    ]


# Create the router
router = APIRouter(tags=["Care"])  # dependency added per-route to allow env gate


@router.post(
    "/ask",
    dependencies=_require_auth_dep(),
    response_model=dict,
)
async def ask_endpoint(
    request: Request,
    body: AskRequest = Body(...),
):
    """Main ask endpoint that routes prompts to appropriate LLM backends.

    This endpoint:
    1. Validates authentication and scope
    2. Processes the prompt through the routing system
    3. Returns streaming or non-streaming responses
    4. Handles errors with appropriate HTTP status codes
    """
    start_time = asyncio.get_event_loop().time()
    request_id = _get_or_generate_request_id(request)
    trace_id = _get_trace_id()

    try:
        with start_span("ask_endpoint", {"rid": request_id}):
            # Extract parameters from request
            prompt_data = body.model_dump(exclude_unset=True)

            # Add request metadata
            prompt_data.update({
                "request_id": request_id,
                "user_id": getattr(request.state, "user_id", "unknown"),
                "trace_id": trace_id,
            })

            # Log the request (redacted)
            logger.info(
                "ask.request",
                extra={
                    "rid": request_id,
                    "user_id": hash_user_id(prompt_data.get("user_id", "unknown")),
                    "payload": _redact_sensitive_data(prompt_data),
                },
            )

            # Route the prompt
            response = await route_prompt(**prompt_data)

            # Log success
            duration = asyncio.get_event_loop().time() - start_time
            logger.info(
                "ask.success",
                extra={
                    "rid": request_id,
                    "duration_ms": duration * 1000,
                    "vendor": response.get("vendor"),
                    "model": response.get("model"),
                },
            )

            return response

    except Exception as e:
        # Log error
        duration = asyncio.get_event_loop().time() - start_time
        logger.error(
            "ask.error",
            exc_info=True,
            extra={
                "rid": request_id,
                "duration_ms": duration * 1000,
                "error_type": type(e).__name__,
                "error_msg": str(e),
            },
        )

        # Return appropriate error response
        if isinstance(e, HTTPException):
            raise

        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "rid": request_id,
                "type": type(e).__name__,
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

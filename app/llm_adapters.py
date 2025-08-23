"""
LLM Adapters Module

This module provides unified interfaces for calling different LLM providers
with consistent error handling and response normalization.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .metrics import MODEL_LATENCY_SECONDS
from .otel_utils import start_span

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common Types and Interfaces
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    model: str
    vendor: str
    metadata: dict[str, Any] | None = None


@dataclass
class LLMRequest:
    """Standardized request to any LLM provider."""

    prompt: str
    model: str
    system_prompt: str | None = None
    stream: bool = False
    on_token: Callable[[str], Awaitable[None]] | None = None
    timeout: float | None = None
    kwargs: dict[str, Any] = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    def __init__(
        self,
        message: str,
        vendor: str,
        model: str,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.vendor = vendor
        self.model = model
        self.original_error = original_error


class LLMTimeoutError(LLMError):
    """Raised when an LLM request times out."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when an LLM request is rate limited."""

    pass


class LLMQuotaError(LLMError):
    """Raised when an LLM quota is exceeded."""

    pass


class LLMProviderError(LLMError):
    """Raised when the LLM provider returns an error."""

    pass


# ---------------------------------------------------------------------------
# Error Normalization
# ---------------------------------------------------------------------------


def normalize_openai_error(error: Exception, model: str) -> LLMError:
    """
    Normalize OpenAI API errors into standard LLMError types.

    Args:
        error: The original OpenAI error
        model: The model that was being used

    Returns:
        A normalized LLMError
    """
    error_str = str(error).lower()

    # Timeout errors
    if "timeout" in error_str or isinstance(error, asyncio.TimeoutError):
        return LLMTimeoutError(
            f"OpenAI request timed out: {error}",
            vendor="openai",
            model=model,
            original_error=error,
        )

    # Rate limit errors
    if "rate limit" in error_str or "429" in error_str:
        return LLMRateLimitError(
            f"OpenAI rate limit exceeded: {error}",
            vendor="openai",
            model=model,
            original_error=error,
        )

    # Quota errors
    if "quota" in error_str or "billing" in error_str or "payment" in error_str:
        return LLMQuotaError(
            f"OpenAI quota exceeded: {error}",
            vendor="openai",
            model=model,
            original_error=error,
        )

    # Provider errors (4xx, 5xx)
    if hasattr(error, "response") and hasattr(error.response, "status_code"):
        status_code = error.response.status_code
        if 400 <= status_code < 500:
            return LLMProviderError(
                f"OpenAI client error ({status_code}): {error}",
                vendor="openai",
                model=model,
                original_error=error,
            )
        elif 500 <= status_code < 600:
            return LLMProviderError(
                f"OpenAI server error ({status_code}): {error}",
                vendor="openai",
                model=model,
                original_error=error,
            )

    # Generic provider error
    return LLMProviderError(
        f"OpenAI error: {error}", vendor="openai", model=model, original_error=error
    )


def normalize_ollama_error(error: Exception, model: str) -> LLMError:
    """
    Normalize Ollama API errors into standard LLMError types.

    Args:
        error: The original Ollama error
        model: The model that was being used

    Returns:
        A normalized LLMError
    """
    error_str = str(error).lower()

    # Timeout errors
    if "timeout" in error_str or isinstance(error, asyncio.TimeoutError):
        return LLMTimeoutError(
            f"Ollama request timed out: {error}",
            vendor="ollama",
            model=model,
            original_error=error,
        )

    # Connection errors
    if "connection" in error_str or "unreachable" in error_str:
        return LLMProviderError(
            f"Ollama connection error: {error}",
            vendor="ollama",
            model=model,
            original_error=error,
        )

    # Model not found
    if "model not found" in error_str or "404" in error_str:
        return LLMProviderError(
            f"Ollama model not found: {error}",
            vendor="ollama",
            model=model,
            original_error=error,
        )

    # Generic provider error
    return LLMProviderError(
        f"Ollama error: {error}", vendor="ollama", model=model, original_error=error
    )


# ---------------------------------------------------------------------------
# OpenAI Adapter
# ---------------------------------------------------------------------------


async def call_openai(request: LLMRequest) -> LLMResponse:
    """
    Call OpenAI with unified interface and error normalization.

    Args:
        request: The LLM request

    Returns:
        Standardized LLM response

    Raises:
        LLMError: Normalized error types
    """
    start_time = time.perf_counter()

    try:
        # Import here to avoid circular imports
        from .gpt_client import ask_gpt

        # Prepare arguments for OpenAI
        kwargs = {}
        if request.timeout is not None:
            kwargs["timeout"] = request.timeout
        if request.stream:
            kwargs["stream"] = True
        if request.on_token:
            kwargs["on_token"] = request.on_token

        # Add any additional kwargs
        kwargs.update(request.kwargs or {})

        # Make the call
        with start_span(
            "openai.chat", {"llm.provider": "openai", "llm.model": request.model}
        ):
            if request.stream:
                # Handle streaming response
                text, pt, ct, cost = await _call_openai_stream(request, kwargs)
            else:
                # Handle non-streaming response
                text, pt, ct, cost = await ask_gpt(
                    request.prompt,
                    model=request.model,
                    system=request.system_prompt,
                    routing_decision=None,
                    **kwargs,
                )

        # Record metrics
        duration = time.perf_counter() - start_time
        MODEL_LATENCY_SECONDS.labels(request.model).observe(duration)

        return LLMResponse(
            text=text,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_usd=cost,
            model=request.model,
            vendor="openai",
        )

    except Exception as e:
        # Normalize the error
        normalized_error = normalize_openai_error(e, request.model)
        logger.error(f"OpenAI call failed: {normalized_error}")
        raise normalized_error


async def _call_openai_stream(
    request: LLMRequest, kwargs: dict[str, Any]
) -> tuple[str, int, int, float]:
    """
    Handle streaming OpenAI calls.

    Args:
        request: The LLM request
        kwargs: Additional arguments

    Returns:
        Tuple of (text, prompt_tokens, completion_tokens, cost)
    """
    from .gpt_client import ask_gpt

    # For streaming, we need to collect the response
    chunks = []

    def token_callback(token: str):
        chunks.append(token)
        if request.on_token:
            asyncio.create_task(request.on_token(token))

    # Make the streaming call
    text, pt, ct, cost = await ask_gpt(
        request.prompt,
        model=request.model,
        system=request.system_prompt,
        stream=True,
        on_token=token_callback,
        routing_decision=None,
        **kwargs,
    )

    return text, pt, ct, cost


# ---------------------------------------------------------------------------
# Ollama Adapter
# ---------------------------------------------------------------------------


async def call_ollama(request: LLMRequest) -> LLMResponse:
    """
    Call Ollama with unified interface and error normalization.

    Args:
        request: The LLM request

    Returns:
        Standardized LLM response

    Raises:
        LLMError: Normalized error types
    """
    start_time = time.perf_counter()

    try:
        # Import here to avoid circular imports
        from .llama_integration import ask_llama

        # Prepare arguments for Ollama
        gen_opts = {}
        if request.timeout is not None:
            gen_opts["timeout"] = request.timeout

        # Add any additional kwargs to gen_opts
        for key, value in (request.kwargs or {}).items():
            if key not in ["timeout"]:  # Don't override timeout
                gen_opts[key] = value

        # Make the call
        with start_span(
            "ollama.chat", {"llm.provider": "ollama", "llm.model": request.model}
        ):
            if request.stream:
                # Handle streaming response
                text, pt, ct, cost = await _call_ollama_stream(request, gen_opts)
            else:
                # Handle non-streaming response
                result = await ask_llama(
                    request.prompt,
                    model=request.model,
                    routing_decision=None,
                    **gen_opts,
                )

                # Extract response components
                if isinstance(result, tuple) and len(result) >= 4:
                    text, pt, ct, cost = result
                else:
                    # Fallback for different response formats
                    text = str(result) if result else ""
                    pt = ct = cost = 0.0

        # Record metrics
        duration = time.perf_counter() - start_time
        MODEL_LATENCY_SECONDS.labels(request.model).observe(duration)

        return LLMResponse(
            text=text,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_usd=cost,
            model=request.model,
            vendor="ollama",
        )

    except Exception as e:
        # Normalize the error
        normalized_error = normalize_ollama_error(e, request.model)
        logger.error(f"Ollama call failed: {normalized_error}")
        raise normalized_error


async def _call_ollama_stream(
    request: LLMRequest, gen_opts: dict[str, Any]
) -> tuple[str, int, int, float]:
    """
    Handle streaming Ollama calls.

    Args:
        request: The LLM request
        gen_opts: Generation options

    Returns:
        Tuple of (text, prompt_tokens, completion_tokens, cost)
    """
    from .llama_integration import ask_llama

    # For streaming, we need to collect the response
    chunks = []

    async def token_callback(token: str):
        chunks.append(token)
        if request.on_token:
            await request.on_token(token)

    # Make the streaming call
    async for token in ask_llama(
        request.prompt, model=request.model, routing_decision=None, **gen_opts
    ):
        await token_callback(token)

    text = "".join(chunks).strip()

    # Estimate tokens and cost for Ollama (since it doesn't provide these)
    pt = len(request.prompt.split())  # Rough estimate
    ct = len(text.split())  # Rough estimate
    cost = 0.0  # Ollama is typically free

    return text, pt, ct, cost


# ---------------------------------------------------------------------------
# Unified Interface
# ---------------------------------------------------------------------------


async def call_llm(request: LLMRequest) -> LLMResponse:
    """
    Unified interface to call any LLM provider.

    Args:
        request: The LLM request

    Returns:
        Standardized LLM response

    Raises:
        LLMError: Normalized error types
    """
    # Determine vendor from model name
    if request.model.startswith("gpt-"):
        return await call_openai(request)
    else:
        return await call_ollama(request)


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------


async def call_openai_simple(
    prompt: str,
    model: str,
    system_prompt: str | None = None,
    timeout: float | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """
    Simple interface for OpenAI calls.

    Args:
        prompt: The user prompt
        model: The model to use
        system_prompt: Optional system prompt
        timeout: Optional timeout in seconds
        **kwargs: Additional arguments

    Returns:
        Standardized LLM response
    """
    request = LLMRequest(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        timeout=timeout,
        **kwargs,
    )
    return await call_openai(request)


async def call_ollama_simple(
    prompt: str, model: str, timeout: float | None = None, **kwargs: Any
) -> LLMResponse:
    """
    Simple interface for Ollama calls.

    Args:
        prompt: The user prompt
        model: The model to use
        timeout: Optional timeout in seconds
        **kwargs: Additional arguments

    Returns:
        Standardized LLM response
    """
    request = LLMRequest(prompt=prompt, model=model, timeout=timeout, **kwargs)
    return await call_ollama(request)

"""Lightweight backend router registry with model routing.

This module provides:
1. Backend registration API for lazy loading
2. Model-to-backend routing logic
3. Standardized backend resolution

Backend routing rules (frozen contract):
- If PROMPT_BACKEND env var is set → use it directly
- Else route by model prefix:
  - gpt-4o*, gpt-4*, gpt-3.5* → openai
  - llama3*, llama2*, llama* → llama
  - Default fallback → dryrun
"""

import os
from collections.abc import Awaitable, Callable
from typing import Any, Optional

_factory: Callable[[str], Callable[[dict], Awaitable[dict]]] | None = None


def register_backend_factory(
    factory: Callable[[str], Callable[[dict], Awaitable[dict]]]
) -> None:
    """Register a backend factory used to resolve backend callables at runtime.

    Keep this registration in startup so imports remain cheap.
    """
    global _factory
    _factory = factory


def get_backend_callable(name: str) -> Callable[[dict], Awaitable[dict]]:
    """Return an async callable for the given backend name.

    Raises RuntimeError if factory not registered or callable cannot be resolved.
    """
    if _factory is None:
        raise RuntimeError("Backend factory not registered")
    return _factory(name)


def resolve_backend(
    model_override: str | None = None, default_backend: str = "dryrun"
) -> str:
    """Resolve backend name from model or environment.

    Frozen routing contract:
    1. If PROMPT_BACKEND env var is set → use it directly
    2. Else route by model prefix:
       - gpt-4o*, gpt-4*, gpt-3.5* → openai
       - llama3*, llama2*, llama* → llama
       - Default → dryrun

    Args:
        model_override: Model name from request (optional)
        default_backend: Fallback backend if no routing matches

    Returns:
        Backend name string
    """
    # Priority 1: Explicit PROMPT_BACKEND environment override
    env_backend = os.getenv("PROMPT_BACKEND", "").strip().lower()
    if env_backend:
        return env_backend

    # Priority 2: Route by model prefix
    if model_override:
        model_lower = model_override.lower().strip()

        # OpenAI models
        if model_lower.startswith(("gpt-4o", "gpt-4", "gpt-3.5")):
            return "openai"

        # LLaMA models
        if model_lower.startswith(("llama3", "llama2", "llama")):
            return "llama"

    # Default fallback
    return default_backend


def get_backend_for_request(
    model_override: str | None = None,
) -> Callable[[dict], Awaitable[dict]]:
    """Get backend callable for a request with automatic model routing.

    Args:
        model_override: Model name from request

    Returns:
        Backend callable

    Raises:
        RuntimeError: If backend factory not registered
    """
    backend_name = resolve_backend(model_override)
    return get_backend_callable(backend_name)

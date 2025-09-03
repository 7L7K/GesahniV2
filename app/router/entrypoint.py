"""Thin entrypoint for routing prompts.

This module provides a lightweight `route_prompt` coroutine that other parts
of the application can call without importing the concrete router type.
"""
from __future__ import annotations

from typing import Any

from .registry import get_router


async def route_prompt(*args: Any, **kwargs: Any) -> Any:
    """Thin compatibility entrypoint that delegates to the configured Router.

    This function accepts either a single `payload: dict` argument or the
    traditional positional style used elsewhere in the codebase
    `(prompt, user_id, **kwargs)`. It builds a payload dictionary when
    necessary and calls the registered router's async `route_prompt` method.

    Raises RuntimeError if no router has been configured.
    """
    router = get_router()

    # If caller passed a single dict-like payload, forward directly
    if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
        return await router.route_prompt(args[0])

    # Otherwise, construct a payload from positional args and kwargs
    payload: dict[str, Any] = {}
    if len(args) >= 1:
        payload["prompt"] = args[0]
    if len(args) >= 2:
        payload["user_id"] = args[1]
    # Merge other kwargs into payload (model_override, stream_cb, etc.)
    payload.update(kwargs)

    return await router.route_prompt(payload)



"""Lightweight router protocol used to avoid circular imports.

This module defines a minimal Protocol that other parts of the
application can import without pulling heavy dependencies.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Router(Protocol):
    """Protocol for a router that can route a prompt payload.

    Implementations must provide an async `route_prompt` method that
    accepts a payload dict and returns a dict response.
    """

    async def route_prompt(self, payload: dict) -> dict:
        """Route the given prompt payload and return a response dict."""
        ...

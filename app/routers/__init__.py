"""Lightweight backend router registry.

This module exposes a tiny registration API so application startup can
wire backend callables (lazy, import-light). Backends themselves live in
`app.routers.openai_router` and `app.routers.llama_router` to keep heavy
imports out of the critical import path.

The registered factory should be a callable `fn(name: str) -> AsyncCallable`.
"""

from typing import Callable, Awaitable, Any


_factory: Callable[[str], Callable[[dict], Awaitable[dict]]] | None = None


def register_backend_factory(factory: Callable[[str], Callable[[dict], Awaitable[dict]]]) -> None:
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



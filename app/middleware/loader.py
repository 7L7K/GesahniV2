"""
Deterministic middleware loader with validation.

This module provides a safe wrapper around app.add_middleware that validates
middleware classes at startup and fails loudly if anything is wrong.
"""

import inspect

from starlette.middleware.base import BaseHTTPMiddleware


def add_mw(app, mw_cls: type[BaseHTTPMiddleware], *, name: str):
    """
    Add middleware with validation - fails loudly on startup if anything is wrong.

    Args:
        app: FastAPI/Starlette app instance
        mw_cls: Middleware class to add
        name: Human-readable name for error messages

    Raises:
        RuntimeError: If middleware class is invalid
    """
    # Validate middleware class is not None
    if mw_cls is None:
        raise RuntimeError(
            f"Middleware '{name}' resolved to None - check imports in app.middleware"
        )

    # Validate it's actually a class
    if not inspect.isclass(mw_cls):
        raise RuntimeError(f"Middleware '{name}' is not a class: {mw_cls!r}")

    # Validate it subclasses BaseHTTPMiddleware
    if not issubclass(mw_cls, BaseHTTPMiddleware):
        raise RuntimeError(
            f"Middleware '{name}' must subclass BaseHTTPMiddleware (got {mw_cls})"
        )

    # Add the middleware
    app.add_middleware(mw_cls)

    # Log successful addition (for debugging)
    import logging

    logger = logging.getLogger(__name__)
    logger.debug(f"✅ Added middleware: {name} ({mw_cls.__name__})")

"""Helper for idempotent OPTIONS route registration to avoid duplicate route errors."""

from fastapi import FastAPI, Response, status


def ensure_options(app: FastAPI, path: str):
    """Register an OPTIONS handler for the given path if it doesn't already exist.

    This prevents duplicate route registration errors when fixtures or tests
    repeatedly set up OPTIONS handlers for the same path.

    Args:
        app: The FastAPI application instance
        path: The route path to register OPTIONS handler for
    """
    # Avoid duplicate route errors in repeated fixture setups
    if any(r.path == path and "OPTIONS" in r.methods for r in app.router.routes):
        return

    @app.options(path, include_in_schema=False)
    def _options_handler():
        return Response(status_code=status.HTTP_204_NO_CONTENT)

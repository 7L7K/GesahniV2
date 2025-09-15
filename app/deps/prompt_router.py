import logging
import os

from fastapi import Request

from app.domain.prompt_router import PromptRouter

logger = logging.getLogger(__name__)


def _default_dryrun():
    async def _dry(payload: dict) -> dict:
        return {"dry_run": True, "echo": payload}

    return _dry


def get_prompt_router(request: Request) -> PromptRouter:
    """Dependency to retrieve the prompt router bound on app.state.

    Falls back to a safe dry-run callable when no router has been bound yet.
    This makes tests and early request handling resilient to startup ordering
    issues while keeping DI explicit for normal operation.
    """
    try:
        pr = getattr(request.app.state, "prompt_router", None)
        if pr is not None:
            return pr
    except Exception as e:
        logger.debug("get_prompt_router: app.state access failed: %s", e)

    # No router bound — choose a safe fallback based on config
    backend = os.getenv("PROMPT_BACKEND", "live").lower()
    if backend == "dryrun":
        return _default_dryrun()

    # If configured for a real backend but not yet bound, raise to signal unavailability
    raise RuntimeError(f"Prompt router not bound and PROMPT_BACKEND={backend}")

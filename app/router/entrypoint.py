"""Temporary compatibility bridge for prompt routing.

This shim forwards to the DI-bound prompt router when possible (the one
bound on ``app.state.prompt_router`` by startup). When running outside a
FastAPI request/app context it falls back to a light-weight config-based
resolver that mirrors the startup logic.  Log usage so we can track legacy
calls and remove this bridge after migration.
"""
from __future__ import annotations

from typing import Dict, Any
import logging
import os

from app.errors import BackendUnavailable

logger = logging.getLogger(__name__)


async def route_prompt(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility entrypoint used by older callers.

    Prefer the DI-bound router on ``app.main.app.state.prompt_router`` when
    available. Otherwise, resolve by configuration (mirrors startup) and
    call the concrete backend module directly.
    """
    # 1) Try to use the running FastAPI app instance if present
    try:
        # Prefer registry-configured router when available (keeps legacy behavior)
        try:
            from .registry import get_router

            router = get_router()
            if router is not None:
                logger.info("compat.route_prompt: using registry router")
                return await router.route_prompt(payload)
        except Exception:
            # registry not configured or unavailable, continue
            pass

        from app.main import app as main_app

        prompt_router = getattr(main_app.state, "prompt_router", None)
        if prompt_router:
            logger.info("compat.route_prompt: using app.state.prompt_router")
            return await prompt_router(payload)
    except Exception as e:  # pragma: no cover - best-effort compatibility
        logger.debug("compat.route_prompt: failed to use app.state (%s)", e)

    # 2) Fallback: light-weight config-based resolver (mirrors startup binding)
    try:
        from app.settings import settings

        backend = getattr(settings, "PROMPT_BACKEND", os.getenv("PROMPT_BACKEND", "dryrun")).lower()
    except Exception:
        backend = os.getenv("PROMPT_BACKEND", "dryrun").lower()

    logger.info("compat.route_prompt: falling back to config resolver backend=%s", backend)

    try:
        if backend == "openai":
            from app.routers.openai_router import openai_router

            logger.warning("compat.route_prompt: calling OpenAI backend via bridge (legacy path)")
            return await openai_router(payload)
        elif backend == "llama":
            from app.routers.llama_router import llama_router

            logger.warning("compat.route_prompt: calling LLaMA backend via bridge (legacy path)")
            return await llama_router(payload)
        else:
            logger.warning("compat.route_prompt: dryrun fallback used (legacy path)")
            return {"dry_run": True, "echo": payload}
    except Exception as e:
        logger.exception("compat.route_prompt: backend call failed: %s", e)
        raise BackendUnavailable(str(e))


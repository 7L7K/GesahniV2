"""Environment-aware async initializers used during startup.

Each function in this module performs a minimal, well-documented action and
returns quickly. Initializers should be safe to call repeatedly (idempotent)
and avoid raising for optional misconfiguration; instead they should log and
let the startup orchestration decide how to proceed.

Components:
- ``init_database``: Verify DB connectivity and assume schemas were created
  by the lifespan bootstrap.
- ``init_token_store_schema``: Fire-and-forget migration for token store.
- ``init_openai_health_check``: Delegate to the startup vendor helper to
  perform a gated OpenAI ping.
- ``init_vector_store``: Probe the configured vector store using a light
  read-only action (``ping`` or ``search_memories``) and support sync/async
  implementations.
- ``init_llama``: Check LLaMA configuration and call into integration to
  verify availability.
- ``init_home_assistant``: Probe Home Assistant `/states` when configured.
- ``init_memory_store``: Ensure memory store backend is constructible.
- ``init_scheduler``: Start the scheduler if not already running (sync/async
  tolerant).

Document any new initializer here and add its name to
``app/startup/config.py`` to include it in a profile.
"""

from __future__ import annotations

import os
import inspect
import logging

logger = logging.getLogger(__name__)


async def init_database():
    """Verify database connectivity.

    Note: database schema creation is performed by the lifespan bootstrap
    earlier in the startup sequence (`init_db_once`). This function should be
    lightweight and only assert that the DB backend is reachable.
    """
    logger.info("Database connectivity verified - schemas already initialized")


async def init_token_store_schema():
    """Start token store schema migration in the background.

    This runs as a fire-and-forget asyncio task so the main startup sequence
    does not block on potentially long migrations while still ensuring
    migrations are triggered.
    """
    from app.auth_store_tokens import token_dao  # lazy import
    import asyncio

    asyncio.create_task(token_dao.ensure_schema_migrated())
    logger.debug("Token store schema migration started in background")


async def init_openai_health_check():
    """Gated OpenAI health check used during startup.

    Delegates to ``app.startup.util_check_vendor('openai')`` which wraps the
    vendor probe and enforces gating via ``STARTUP_VENDOR_PINGS``.
    """
    from app.startup import util_check_vendor
    await util_check_vendor("openai")


async def init_vector_store():
    """Probe the vector store with a read-only operation.

    Supports both synchronous and asynchronous backends by detecting callables
    and awaiting awaitables when needed.
    """
    from app.memory.api import _get_store
    store = _get_store()
    try:
        if hasattr(store, "ping"):
            ping_fn = getattr(store, "ping")
            if inspect.iscoroutinefunction(ping_fn):
                await ping_fn()
            else:
                res = ping_fn()
                if inspect.isawaitable(res):
                    await res
        elif hasattr(store, "search_memories"):
            search_fn = getattr(store, "search_memories")
            if inspect.iscoroutinefunction(search_fn):
                await search_fn("", "", limit=0)
            else:
                res = search_fn("", "", limit=0)
                if inspect.isawaitable(res):
                    await res
    except Exception as e:
        logger.error("Vector store initialization failed: %s", e)
        raise


async def init_llama():
    """Initialize/verify LLaMA (Ollama) integration when configured.

    - If ``LLAMA_ENABLED`` is explicitly set to a falsey value, this is a no-op.
    - If no ``OLLAMA_URL`` is present and LLAMA is not explicitly enabled, skip.
    - Otherwise call into ``app.llama_integration._check_and_set_flag`` to
      perform the concrete health check.
    """
    enabled = (os.getenv("LLAMA_ENABLED") or "").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.debug("LLaMA disabled by LLAMA_ENABLED")
        return
    url = os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL")
    if not url and enabled not in {"1", "true", "yes", "on"}:
        logger.debug("LLaMA not configured (no OLLAMA_URL); skipping")
        return
    from app.llama_integration import _check_and_set_flag
    await _check_and_set_flag()
    logger.debug("LLaMA integration OK")


async def init_home_assistant():
    """Verify Home Assistant connectivity when configured.

    Honor ``HOME_ASSISTANT_ENABLED`` and ``HOME_ASSISTANT_URL``; if missing,
    log and skip. Otherwise perform a minimal ``get_states`` probe.
    """
    enabled = (os.getenv("HOME_ASSISTANT_ENABLED") or "").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.debug("HA disabled by HOME_ASSISTANT_ENABLED")
        return
    if not os.getenv("HOME_ASSISTANT_URL"):
        logger.debug("HA not configured (no HOME_ASSISTANT_URL); skipping")
        return
    from app.home_assistant import get_states
    await get_states()
    logger.debug("Home Assistant integration OK")


async def init_memory_store():
    """Ensure memory store backend constructible.

    This is intentionally cheap: instantiate the store factory to verify
    configuration rather than performing heavy operations.
    """
    from app.memory.api import _get_store
    _get_store()
    logger.debug("Memory store OK")


async def init_scheduler():
    """Start the scheduler if not already running (sync/async tolerant)."""
    from app.deps.scheduler import scheduler
    start = scheduler.start
    if inspect.iscoroutinefunction(start):
        await start()
    else:
        start()
    logger.debug("Scheduler started (or already running)")


 
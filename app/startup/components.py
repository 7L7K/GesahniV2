# app/startup/components.py
from __future__ import annotations
import os
import inspect
import logging

logger = logging.getLogger(__name__)

async def init_database():
    # Schemas should already be created by db.init_db_once (called by lifespan).
    logger.info("Database connectivity verified - schemas already initialized")

async def init_token_store_schema():
    from app.auth_store_tokens import token_dao  # lazy import
    import asyncio
    asyncio.create_task(token_dao.ensure_schema_migrated())
    logger.debug("Token store schema migration started in background")

async def init_openai_health_check():
    from app.startup import util_check_vendor  # local helper we'll add in __init__.py
    await util_check_vendor("openai")

async def init_vector_store():
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
    from app.memory.api import _get_store
    _get_store()
    logger.debug("Memory store OK")

async def init_scheduler():
    from app.deps.scheduler import scheduler
    start = scheduler.start
    if inspect.iscoroutinefunction(start):
        await start()
    else:
        start()
    logger.debug("Scheduler started (or already running)")

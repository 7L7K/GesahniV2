"""Startup package orchestrator.

This module exposes the canonical ``lifespan`` context manager used by the
application to perform environment-first startup and orderly shutdown. It
delegates to small initializer functions in ``app.startup.components`` and
uses ``app.startup.config.detect_profile`` to decide which components to run
for a given runtime profile (`dev`/`prod`/`ci`).

Design goals:

- Keep initializers minimal and idempotent so they can be exercised in tests
  and locally without side-effects.
- Gate expensive vendor probes behind environment flags.
- Log and continue on optional external failures to keep boot resilient.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Set

from fastapi import FastAPI

from app.routers import normalize_backend_name
from app.security.module_loader import secure_import_attr, secure_load_router
from app.startup import components as C
from app.startup.config import detect_profile
from app.startup.config_guard import assert_strict_prod

# --- begin addition: background task registry ---
_background_tasks: set[asyncio.Task] = set()


def start_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(lambda t: _background_tasks.discard(t))
    return task


async def cancel_background_tasks(timeout: float = 2.0) -> None:
    if not _background_tasks:
        return
    for t in list(_background_tasks):
        t.cancel()
    try:
        await asyncio.wait(_background_tasks, timeout=timeout)
    except Exception:
        pass
    _background_tasks.clear()


# --- end addition ---

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager used by the app instance.

    Responsibilities:
    - Ensure DB schemas are created once via ``init_db_once``.
    - Run environment-aware startup components with per-step timeouts.
    - Launch optional background daemons (best-effort).
    - Bind prompt backend and perform app-specific startup tasks.
    - Perform graceful shutdown/cleanup.
    """
    # 1) DB schema once, before component inits
    await _init_db_once()

    # 2) Environment-aware component startup with timeouts + error capture
    await _run_components()

    # Router registration lives in create_app(); no HTTP mounts here.

    # 3) Initialize WebSocket LRU cache
    try:
        from app.utils.lru_cache import init_ws_idempotency_cache

        await init_ws_idempotency_cache()
        logger.info("✅ WebSocket LRU cache initialized")
    except Exception as e:
        logger.warning("⚠️ WebSocket LRU cache initialization failed: %s", e)

    # 4) Bind prompt backend to app.state
    await _bind_prompt_backend(app)

    # 5) Diagnostic startup event (only when DEBUG=1)
    await _diag_start(app)

    # 6) Auth cookie config dump (only when AUTH_DEBUG=1)
    await _auth_cookie_cfg_dump(app)

    # 7) Fire-and-forget daemons that are optional
    _start_daemons()

    try:
        yield
    finally:
        # Diagnostic shutdown event (only when DEBUG=1)
        await _diag_stop(app)
        await _shutdown(app)


async def _bind_prompt_backend(app: FastAPI):
    """Bind prompt backend to app.state."""
    try:
        # Defer settings import to avoid side-effects at module import
        from app.settings import settings

        backend = getattr(
            settings, "PROMPT_BACKEND", os.getenv("PROMPT_BACKEND", "live")
        ).lower()
    except Exception:
        backend = os.getenv("PROMPT_BACKEND", "live").lower()

    raw_backend = backend
    backend = normalize_backend_name(backend)

    if raw_backend == "live":
        if backend == "dryrun":
            logger.warning(
                "PROMPT_BACKEND=live but no vendor configured; using dryrun backend"
            )
        else:
            logger.info("PROMPT_BACKEND=live resolved to %s backend", backend)

    if backend == "openai":
        from app.routers.openai_router import openai_router

        app.state.prompt_router = openai_router
        logger.info("prompt backend bound: openai")
    elif backend == "llama":
        from app.routers.llama_router import llama_router

        app.state.prompt_router = llama_router
        logger.info("prompt backend bound: llama")
    elif backend == "dryrun":

        async def dryrun_router(payload: dict) -> dict:
            return {"dry_run": True, "echo": payload}

        app.state.prompt_router = dryrun_router
        logger.info("prompt backend bound: dryrun (safe default)")
    else:
        # For "live" or other backends, try to dynamically resolve the router
        try:
            # Try to import the router module securely
            router = secure_load_router(
                f"app.routers.{backend}_router:{backend}_router"
            )
            app.state.prompt_router = router
            logger.info(f"prompt backend bound: {backend}")
        except Exception:
            # If dynamic import fails, fall back to dryrun
            async def dryrun_router(payload: dict) -> dict:
                return {
                    "dry_run": True,
                    "echo": payload,
                    "error": f"Unknown backend: {backend}",
                }

            app.state.prompt_router = dryrun_router
            logger.warning(
                f"Unknown PROMPT_BACKEND={backend!r}, falling back to dryrun"
            )


async def _diag_start(app: FastAPI):
    """Diagnostic startup event (only when DEBUG=1)."""
    if os.getenv("GSN_DEBUG_STARTUP") == "1":
        try:
            from app.diagnostics.state import record_event

            record_event("startup", "application startup")
        except Exception:
            pass


async def _auth_cookie_cfg_dump(app: FastAPI):
    """Auth cookie config dump (only when AUTH_DEBUG=1)."""
    try:
        if os.getenv("AUTH_DEBUG") == "1":
            from app.startup.auth_config_dump import dump_cookie_config

            dump_cookie_config()
    except Exception:
        # Never fail startup due to debug logging
        pass


async def _diag_stop(app: FastAPI):
    """Diagnostic shutdown event (only when DEBUG=1)."""
    if os.getenv("GSN_DEBUG_STARTUP") == "1":
        try:
            from app.diagnostics.state import record_event

            record_event("shutdown", "application shutdown")
        except Exception:
            pass


async def _init_db_once():
    try:
        from app.db import init_db_once

        await init_db_once()
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise


async def _run_components():
    # 1) Strict production configuration guardrails (fails fast)
    try:
        assert_strict_prod()
    except Exception as e:
        logger.error("❌ Production configuration validation failed: %s", e)
        raise

    # 2) Environment-aware component startup
    profile = detect_profile()
    logger.info("Startup profile: %s", profile.name)

    name_to_callable: dict[str, Callable[[], Awaitable[None]]] = {
        "init_database": C.init_database,
        "init_database_migrations": C.init_database_migrations,
        "init_token_store_schema": C.init_token_store_schema,
        "init_openai_health_check": C.init_openai_health_check,
        "init_vector_store": C.init_vector_store,
        "init_llama": C.init_llama,
        "init_home_assistant": C.init_home_assistant,
        "init_memory_store": C.init_memory_store,
        "init_scheduler": C.init_scheduler,
        "init_dev_user": C.init_dev_user,
        "init_chaos_mode": C.init_chaos_mode,
        "init_client_warmup": C.init_client_warmup,
        "init_feature_flags_logging": C.init_feature_flags_logging,
    }

    for idx, comp_name in enumerate(profile.components, 1):
        fn = name_to_callable[comp_name]
        started = time.time()
        try:
            await asyncio.wait_for(
                fn(), timeout=float(os.getenv("STARTUP_STEP_TIMEOUT", "30"))
            )
            logger.info(
                "✅ [%d/%d] %s ok (%.1fs)",
                idx,
                len(profile.components),
                comp_name,
                time.time() - started,
            )
        except TimeoutError:
            logger.warning("⚠️ %s timed out; continuing", comp_name)
        except Exception as e:
            logger.warning("⚠️ %s failed: %s; continuing", comp_name, e)


def _start_daemons():
    # These are best-effort; never fatal
    # Skip starting long-running daemons when running in CI/test to avoid
    # event-loop conflicts with the test harness.
    try:
        profile = detect_profile()
        if profile.name == "ci" or os.getenv("PYTEST_RUNNING"):
            logger.debug("Skipping background daemons in CI/test profile")
            return
    except Exception:
        # If detect_profile fails for any reason, fall back to proceeding
        pass
    try:
        from app.care_daemons import heartbeat_monitor_loop

        start_background_task(heartbeat_monitor_loop())
    except Exception:
        logger.debug("heartbeat_monitor_loop not started", exc_info=True)

    try:
        from app.api.sms_queue import sms_worker

        start_background_task(sms_worker())
    except Exception:
        logger.debug("sms_worker not started", exc_info=True)

    try:
        from app.router_legacy import start_openai_health_background_loop

        start_openai_health_background_loop()
    except Exception:
        logger.debug("OpenAI health background loop not started", exc_info=True)


async def _shutdown(app: FastAPI):
    # Mark offline for health
    try:
        from app.main import _HEALTH_LAST  # temporary until we relocate health cache

        if _HEALTH_LAST.get("online", True):
            logger.info("healthz status=offline")
        _HEALTH_LAST["online"] = False
    except Exception:
        pass

    # Close clients (best effort)
    for closer_path in (
        "app.gpt_client:close_client",
        "app.transcription:close_whisper_client",
    ):
        try:
            closer = secure_import_attr(*closer_path.split(":", 1))
            res = closer()
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            logger.debug("shutdown cleanup failed for %s", closer_path, exc_info=True)

    # Scheduler shutdown (sync/async tolerant)
    try:
        from app.deps.scheduler import shutdown as scheduler_shutdown  # type: ignore

        if asyncio.iscoroutinefunction(scheduler_shutdown):  # type: ignore[attr-defined]
            await scheduler_shutdown()  # type: ignore[misc]
        else:
            scheduler_shutdown()  # type: ignore[misc]
    except Exception:
        logger.debug("scheduler shutdown failed", exc_info=True)

    # Cancel background tasks first to stop new DB calls
    try:
        await cancel_background_tasks()
    except Exception:
        logger.debug("background task cancellation failed", exc_info=True)

    try:
        from app.application.startup import cancel_startup_tasks

        await cancel_startup_tasks()
    except Exception:
        logger.debug("startup task cancellation failed", exc_info=True)

    # Token store cleanup
    try:
        from app.token_store import stop_cleanup_task

        await stop_cleanup_task()
    except Exception:
        logger.debug("token store cleanup stop failed", exc_info=True)

    # Close DAOs best-effort
    try:
        from app.user_store import close_user_store  # async
    except Exception:

        async def close_user_store():  # type: ignore
            return None

    try:
        from app.skills.notes_skill import close_notes_dao  # async
    except Exception:

        async def close_notes_dao():  # type: ignore
            return None

    try:
        from app.auth_store_tokens import close_token_dao  # sync
    except Exception:

        def close_token_dao():  # type: ignore
            return None

    try:
        await close_user_store()
    except Exception:
        logger.debug("close_user_store failed", exc_info=True)

    try:
        await close_notes_dao()
    except Exception:
        logger.debug("close_notes_dao failed", exc_info=True)

    try:
        close_token_dao()
    except Exception:
        logger.debug("close_token_dao failed", exc_info=True)

    # Dispose SQLAlchemy async engines
    try:
        from app.db.core import dispose_engines

        await dispose_engines()
    except Exception:
        logger.debug("dispose_engines failed", exc_info=True)


# util used by components.init_openai_health_check
async def util_check_vendor(vendor: str):
    from app.startup.vendor import check_vendor_health_gated

    await check_vendor_health_gated(vendor)


# Re-exported helper for components that want a stricter vendor probe
async def vendor_health(vendor: str):
    try:
        from app.startup.vendor import check_vendor_health_gated

        res = await check_vendor_health_gated(vendor)
        if res.get("status") not in {"healthy", "skipped", "missing_config"}:
            msg = res.get("error") or res.get("reason") or f"vendor {vendor} unhealthy"
            raise RuntimeError(msg)
    except Exception:
        raise


__all__ = ["lifespan", "util_check_vendor", "vendor_health", "detect_profile"]

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Any

from app.application.error_monitoring import record_error
from app.storytime import schedule_nightly_jobs

logger = logging.getLogger(__name__)

STARTUP_TASKS: list[asyncio.Task[Any]] = []


def proactive_startup() -> None:
    """Best-effort bootstrap for the proactive engine."""
    try:
        from app.proactive_engine import startup as _start

        _start()
    except Exception:
        return None


def enforce_jwt_strength() -> None:
    """Validate the JWT secret strength based on environment settings."""
    secret = os.getenv("JWT_SECRET", "") or ""
    env = os.getenv("ENV", "").strip().lower()
    dev_mode = os.getenv("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}

    def _is_dev() -> bool:
        return env == "dev" or dev_mode

    if len(secret) >= 32:
        logger.info("JWT secret: OK (len=%d)", len(secret))
        return

    if _is_dev():
        logger.warning(
            "JWT secret: WEAK (len=%d) — allowed in dev/tests only", len(secret)
        )
        return

    raise RuntimeError("JWT_SECRET too weak (need >= 32 characters)")


async def enhanced_startup() -> None:
    """Enhanced startup with comprehensive error tracking and logging."""
    startup_start = time.time()
    logger.info("Starting enhanced application startup")

    # Log resolved configuration values (safe subset only)
    safe_config = {
        "ENV": os.getenv("ENV"),
        "HOST": os.getenv("HOST"),
        "PORT": os.getenv("PORT"),
        "LOG_LEVEL": os.getenv("LOG_LEVEL"),
        "COOKIE_SAMESITE": os.getenv("COOKIE_SAMESITE"),
        "COOKIE_SECURE": os.getenv("COOKIE_SECURE"),
        "CSRF_ENABLED": os.getenv("CSRF_ENABLED"),
        "CORS_ALLOW_ORIGINS": os.getenv("CORS_ALLOW_ORIGINS"),
        "VECTOR_STORE": os.getenv("VECTOR_STORE"),
        "QDRANT_URL": os.getenv("QDRANT_URL"),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL"),
        "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL"),
    }
    logger.info("Resolved config: %s", safe_config)

    try:
        from app.secret_verification import audit_prod_env, log_secret_summary

        log_secret_summary()

        try:
            enforce_jwt_strength()
        except Exception as exc:
            logger.error("JWT secret validation failed: %s", exc)
            record_error(exc, "startup.jwt_secret")
            raise

        try:
            audit_prod_env()
        except Exception as exc:
            logger.error("Production environment audit failed: %s", exc)
            record_error(exc, "startup.prod_audit")
            raise

        try:
            from app.startup.components import (
                init_database,
                init_database_migrations,
                init_home_assistant,
                init_memory_store,
                init_openai_health_check,
                init_scheduler,
                init_token_store_schema,
                init_vector_store,
            )

            components = [
                ("Database", init_database),
                ("Database Migrations", init_database_migrations),
                ("Token Store Schema", init_token_store_schema),
                ("OpenAI Health Check", init_openai_health_check),
                ("Vector Store", init_vector_store),
                ("Home Assistant", init_home_assistant),
                ("Memory Store", init_memory_store),
                ("Scheduler", init_scheduler),
            ]
        except Exception as exc:
            logger.warning("Failed to import startup components: %s", exc)
            components = []

        total_components = len(components)
        for index, (name, init_func) in enumerate(components, 1):
            try:
                start_time = time.time()
                logger.info("[%d/%d] Initializing %s...", index, total_components, name)
                task = asyncio.create_task(init_func())
                _track_startup_task(task)
                try:
                    await asyncio.wait_for(task, timeout=30.0)
                    duration = time.time() - start_time
                    logger.info(
                        "✅ %s initialized successfully (%.1fs)", name, duration
                    )
                except TimeoutError:
                    logger.warning(
                        "⚠️ %s initialization timed out after 30s - continuing startup",
                        name,
                    )
                    record_error(
                        TimeoutError(f"{name} init timeout"),
                        f"startup.{name.lower().replace(' ', '_')}",
                    )
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                except Exception as exc:
                    duration = time.time() - start_time
                    logger.warning("⚠️ %s failed after %.1fs: %s", name, duration, exc)
                    record_error(exc, f"startup.{name.lower().replace(' ', '_')}")
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
            except Exception as exc:
                logger.error(
                    "Critical error initializing %s: %s", name, exc, exc_info=True
                )
                record_error(exc, f"startup.{name.lower().replace(' ', '_')}")

        try:
            schedule_nightly_jobs()
        except Exception as exc:
            logger.debug("schedule_nightly_jobs failed", exc_info=True)
            record_error(exc, "startup.nightly_jobs")

        try:
            proactive_startup()
        except Exception as exc:
            logger.debug("proactive_startup failed", exc_info=True)
            record_error(exc, "startup.proactive")

        try:
            from app.token_store import start_cleanup_task

            await start_cleanup_task()
        except Exception as exc:
            logger.debug("token store cleanup task not started", exc_info=True)
            record_error(exc, "startup.token_store")

        startup_time = time.time() - startup_start
        logger.info("Application startup completed in %.2fs", startup_time)
    except Exception as exc:
        logger.error("Critical startup failure: %s", exc, exc_info=True)
        record_error(exc, "startup.critical")
        raise


def _track_startup_task(task: asyncio.Task[Any]) -> None:
    STARTUP_TASKS.append(task)

    def _cleanup(done_task: asyncio.Task[Any]) -> None:
        with contextlib.suppress(ValueError):
            STARTUP_TASKS.remove(done_task)

    task.add_done_callback(_cleanup)


async def cancel_startup_tasks(timeout: float = 2.0) -> None:
    if not STARTUP_TASKS:
        return
    pending = [t for t in list(STARTUP_TASKS) if not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        with contextlib.suppress(Exception):
            await asyncio.wait(pending, timeout=timeout)
    STARTUP_TASKS.clear()


__all__ = [
    "enhanced_startup",
    "enforce_jwt_strength",
    "proactive_startup",
    "cancel_startup_tasks",
]

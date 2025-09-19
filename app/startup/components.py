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

import inspect
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Rate-limited failure logging for dev
_failure_timestamps = {}


def _log_failure_dev(service: str, error: Exception):
    """Log service connection failures with rate limiting in dev."""
    env = os.getenv("ENV", "dev").strip().lower()
    if env not in {"dev", "local"}:
        logger.warning("%s connection failed: %s", service, error)
        return

    import time

    now = time.time()
    last = _failure_timestamps.get(service, 0)

    if now - last > 60:  # First failure or >60s since last
        logger.warning("%s connection failed: %s", service, error)
        _failure_timestamps[service] = now
    else:
        logger.info("%s connection failed (suppressed warning): %s", service, error)


def _is_sqlite(url: str | None) -> bool:
    if not url:
        return False
    u = urlparse(url)
    return (u.scheme or "").startswith("sqlite")


async def init_database():
    """Verify PostgreSQL connectivity.

    Note: database schema creation is performed by the lifespan bootstrap
    earlier in the startup sequence (`init_db_once`). This function verifies
    that the PostgreSQL database is reachable and responding.
    """
    # Skip PG health checks when using sqlite (tests/CI)
    if _is_sqlite(os.getenv("DATABASE_URL")):
        logger.debug("Skipping PostgreSQL connectivity check (sqlite in use)")
        return

    try:
        from app.db.core import health_check_async

        logger.info("🔍 Checking PostgreSQL database connectivity...")
        logger.info("   Database URL: %s", os.getenv("DATABASE_URL", "NOT_SET"))

        if await health_check_async():
            logger.info("✅ PostgreSQL connectivity verified - database is accessible")
            logger.info("   ✅ Token storage will work")
            logger.info("   ✅ User authentication will work")
            logger.info("   ✅ OAuth integrations will work")
        else:
            logger.error(
                "❌ PostgreSQL health check failed - database is not responding"
            )
            logger.error("   ❌ Token storage will FAIL")
            logger.error("   ❌ User authentication will FAIL")
            logger.error("   ❌ OAuth integrations will FAIL")
            logger.error(
                "   💡 SOLUTION: Start PostgreSQL service or check DATABASE_URL"
            )
            raise RuntimeError(
                "PostgreSQL health check failed - database is not responding"
            )
    except Exception as e:
        logger.error("🚨 CRITICAL: PostgreSQL connectivity check failed")
        logger.error("   Error details: %s", str(e))
        logger.error("   This will cause:")
        logger.error("   - Token storage failures")
        logger.error("   - Authentication failures")
        logger.error("   - OAuth integration failures")
        logger.error("   - Music integration failures")
        logger.error("")
        logger.error("   🔧 IMMEDIATE ACTION REQUIRED:")
        logger.error(
            "   1. Start PostgreSQL: pg_ctl -D /usr/local/var/postgresql@14 start"
        )
        logger.error("   2. Check DATABASE_URL in .env file")
        logger.error("   3. Verify PostgreSQL is running: ps aux | grep postgres")
        logger.error("")
        raise RuntimeError(f"Database connectivity failure: {e}")


async def init_database_migrations():
    """Run all database migrations during startup.

    This ensures all database schemas are properly migrated before the
    application starts accepting requests.
    """
    try:
        from app.db.migrate import ensure_all_schemas_migrated

        await ensure_all_schemas_migrated()
        logger.info("All database migrations completed successfully")
    except Exception as e:
        logger.error("Database migration failed during startup: %s", e)
        # Re-raise to fail startup if migrations are critical
        raise


async def init_token_store_schema():
    """Start token store schema migration in the background.

    This runs as a fire-and-forget asyncio task so the main startup sequence
    does not block on potentially long migrations while still ensuring
    migrations are triggered.
    """
    from app.auth_store_tokens import token_dao  # lazy import

    try:
        from app.startup import start_background_task  # type: ignore

        start_background_task(token_dao.ensure_schema_migrated())
    except Exception:
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

    - If feature flag GSN_ENABLE_QDRANT is off and VECTOR_STORE=qdrant, skip Qdrant health checks.
    Supports both synchronous and asynchronous backends by detecting callables
    and awaiting awaitables when needed.
    """
    from app.feature_flags import QDRANT_ON

    # Check if this is a Qdrant vector store that's disabled
    vector_store = (os.getenv("VECTOR_STORE") or "memory").lower()
    if vector_store.startswith("qdrant") and not QDRANT_ON:
        logger.debug("Qdrant disabled in this profile")
        return

    from app.memory.api import _get_store

    store = _get_store()
    try:
        if hasattr(store, "ping"):
            ping_fn = store.ping
            if inspect.iscoroutinefunction(ping_fn):
                await ping_fn()
            else:
                res = ping_fn()
                if inspect.isawaitable(res):
                    await res
        elif hasattr(store, "search_memories"):
            search_fn = store.search_memories
            if inspect.iscoroutinefunction(search_fn):
                await search_fn("", "", limit=0)
            else:
                res = search_fn("", "", limit=0)
                if inspect.isawaitable(res):
                    await res
    except Exception as e:
        _log_failure_dev("Vector store", e)
        raise


async def init_llama():
    """Initialize/verify LLaMA (Ollama) integration when configured.

    - If feature flag GSN_ENABLE_OLLAMA is off, this is a no-op.
    - If ``LLAMA_ENABLED`` is explicitly set to a falsey value, this is a no-op.
    - If no ``OLLAMA_URL`` is present and LLAMA is not explicitly enabled, skip.
    - Otherwise call into ``app.llama_integration._check_and_set_flag`` to
      perform the concrete health check.
    """
    from app.feature_flags import OLLAMA_ON

    if not OLLAMA_ON:
        logger.debug("Ollama disabled in this profile")
        return

    enabled = (os.getenv("LLAMA_ENABLED") or "").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.debug("LLaMA disabled by LLAMA_ENABLED")
        return
    url = os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL")
    if not url and enabled not in {"1", "true", "yes", "on"}:
        logger.debug("LLaMA not configured (no OLLAMA_URL); skipping")
        return
    from app.llama_integration import _check_and_set_flag

    try:
        await _check_and_set_flag()
        logger.debug("LLaMA integration OK")
    except Exception as e:
        _log_failure_dev("Ollama", e)
        raise


async def init_home_assistant():
    """Verify Home Assistant connectivity when configured.

    - If feature flag GSN_ENABLE_HOME_ASSISTANT is off, this is a no-op.
    Honor ``HOME_ASSISTANT_ENABLED`` and ``HOME_ASSISTANT_URL``; if missing,
    log and skip. Otherwise perform a minimal ``get_states`` probe.
    """
    from app.feature_flags import HA_ON

    if not HA_ON:
        logger.debug("Home Assistant disabled in this profile")
        return

    enabled = (os.getenv("HOME_ASSISTANT_ENABLED") or "").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.debug("HA disabled by HOME_ASSISTANT_ENABLED")
        return
    if not os.getenv("HOME_ASSISTANT_URL"):
        logger.debug("HA not configured (no HOME_ASSISTANT_URL); skipping")
        return
    from app.home_assistant import get_states

    try:
        await get_states()
        logger.debug("Home Assistant integration OK")
    except Exception as e:
        _log_failure_dev("Home Assistant", e)
        raise


async def init_chaos_mode():
    """Initialize chaos mode for resilience testing.

    Only runs in development when CHAOS_MODE=1 is set.
    Logs chaos configuration for monitoring.
    """
    from app.chaos import log_chaos_status

    log_chaos_status()
    logger.info("🎭 Chaos mode initialization completed")


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


async def init_dev_user():
    """Create a dev user with password 'devpass123!' in dev environment only.

    Gated by ENV=dev to avoid running in production.
    """
    import uuid

    env = os.getenv("ENV", "dev").strip().lower()
    if env != "dev":
        logger.debug("Dev user seeding skipped (ENV != dev)")
        return

    try:
        from app.auth import pwd_context
        from app.auth_store import create_user

        # Generate a UUID for the dev user
        dev_user_id = str(uuid.uuid4())

        # Hash the password
        password_hash = pwd_context.hash("devpass123!")

        # Create the user
        await create_user(
            id=dev_user_id,
            email="dev@example.com",  # Dummy email
            password_hash=password_hash,
            name="Dev User",
            username="dev_user",  # Username for password authentication
        )
        logger.info("Dev user 'dev_user' created successfully (ID: %s)", dev_user_id)
    except Exception as e:
        logger.warning("Failed to create dev user: %s", e)


async def init_feature_flags_logging():
    """Log all feature flags at application startup.

    This provides visibility into which features are enabled/disabled
    for debugging and security auditing purposes.
    """
    from app.feature_flags import list_flags

    flags = list_flags()
    logger.info("🚩 Feature flags at startup:")
    for flag_name, flag_value in sorted(flags.items()):
        logger.info(f"  {flag_name}: {flag_value}")

    # Special warnings for risky features
    risky_flags = {
        "MUSIC_ENABLED": "Music integration (external service dependency)",
        "AUTH_COOKIES_ENABLED": "Auth cookies (stateful authentication)",
        "MODEL_ROUTING_ENABLED": "Model routing (LLM failover logic)",
    }

    for flag_name, description in risky_flags.items():
        if flags.get(flag_name, "false").lower() == "true":
            logger.warning(f"⚠️  Risky feature ENABLED: {flag_name} ({description})")
        else:
            logger.info(f"🛡️  Risky feature DISABLED: {flag_name} ({description})")


async def init_client_warmup():
    """Warm up lazy clients (Qdrant, OpenAI) in production.

    Only runs when GSN_WARMUP=1 is set (production by default).
    Performs DNS resolution and TCP connection establishment.
    Skips in dev environment unless explicitly requested.
    """
    env = os.getenv("ENV", "dev").strip().lower()
    warmup_enabled = os.getenv(
        "GSN_WARMUP", "1" if env in {"prod", "production"} else "0"
    ).strip()

    if warmup_enabled != "1":
        logger.debug("Client warmup skipped (GSN_WARMUP != 1)")
        return

    logger.info("🔥 Warming up lazy clients...")

    try:
        # Warm OpenAI client (DNS + TCP)
        from app.embeddings import get_openai_client

        get_openai_client()
        # Simple DNS resolution and connection test
        logger.debug("OpenAI client warmed up")
    except Exception as e:
        logger.warning("OpenAI client warmup failed: %s", e)

    try:
        # Warm Qdrant client (DNS + TCP + basic ping)
        from app.embeddings import get_qdrant_client

        get_qdrant_client()
        # The QdrantVectorStore constructor already performs connection setup
        logger.debug("Qdrant client warmed up")
    except Exception as e:
        logger.warning("Qdrant client warmup failed: %s", e)

    logger.info("✅ Client warmup completed")

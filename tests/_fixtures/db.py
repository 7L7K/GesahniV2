import asyncio
import os

import pytest

# Make tests deterministic and isolated
os.environ.setdefault("ENV", "test")
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("ASGI_AUTO_APP", "1")
# Use PostgreSQL for tests (container is running on port 5432)
os.environ.setdefault(
    "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni_test"
)
# Disable anything that reaches out to the world
os.environ.setdefault("OTEL_ENABLED", "0")
os.environ.setdefault("PROMETHEUS_ENABLED", "0")
os.environ.setdefault("STRICT_VECTOR_STORE", "0")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def _migrations():
    """
    Ensure schemas exist before any test runs. Use the app's own migration APIs.
    """
    # Debug: Print current DATABASE_URL
    import os

    print(f"DEBUG: DATABASE_URL in _migrations fixture: {os.getenv('DATABASE_URL')}")

    # Force reload of db.core module to pick up the new DATABASE_URL
    import importlib

    import app.db.core

    importlib.reload(app.db.core)

    # Debug: Check what DATABASE_URL the reloaded module sees
    print(f"DEBUG: app.db.core.DATABASE_URL: {app.db.core.DATABASE_URL}")

    try:
        # If you have a unified migration entrypoint, prefer that.
        from app.startup.components import init_database, init_database_migrations

        await init_database()
        await init_database_migrations()
    except Exception:
        # Fallback: token store might have its own migrator
        try:
            from app.auth_store_tokens import token_dao

            await token_dao.ensure_schema_migrated()
        except Exception:
            # Don't block the suite; tests that need DB will fail explicitly and point here.
            pass

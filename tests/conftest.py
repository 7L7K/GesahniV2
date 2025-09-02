"""Test-specific fixtures."""

import os
import tempfile
import pytest
import asyncio
from starlette.testclient import TestClient as _TestClient


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db_and_init_tables():
    """Guarantee DB tables exist before any tests touch the databases.

    This fixture runs once per test session and ensures all database tables
    are created before any test code runs, preventing sqlite3.OperationalError.
    """
    # Mark that we're running tests
    os.environ["PYTEST_RUNNING"] = "1"

    # Set up test database directory - use a dedicated temp directory for tests
    test_db_dir = os.path.join(tempfile.gettempdir(), "gesahni_test_dbs")
    os.environ["GESAHNI_TEST_DB_DIR"] = test_db_dir

    # Ensure the test directory exists
    os.makedirs(test_db_dir, exist_ok=True)

    # Initialize ALL database tables synchronously (since pytest fixtures run in sync context)
    async def init_tables():
        from app.db import init_all_tables
        await init_all_tables()

    # Create event loop if needed and run the initialization
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running (e.g., in pytest-asyncio), schedule the coroutine
            loop.create_task(init_tables())
        else:
            loop.run_until_complete(init_tables())
    except RuntimeError:
        # No event loop, create one
        asyncio.run(init_tables())


@pytest.fixture(autouse=True)
def _reset_llama_health(monkeypatch):
    """Ensure ``LLAMA_HEALTHY`` starts True for each test and silence OTEL."""
    from app import llama_integration

    llama_integration.LLAMA_HEALTHY = True
    # Silence OpenTelemetry exporter during tests to avoid noisy connection errors
    monkeypatch.setenv("OTEL_ENABLED", "0")


# TestClient shim to handle allow_redirects parameter compatibility
class TestClient(_TestClient):
    """Extended TestClient that handles allow_redirects parameter for compatibility."""

    def get(self, *args, **kwargs):
        # Remove allow_redirects if present to avoid "unexpected keyword argument" errors
        kwargs.pop("allow_redirects", None)
        return super().get(*args, **kwargs)

    def post(self, *args, **kwargs):
        # Remove allow_redirects if present to avoid "unexpected keyword argument" errors
        kwargs.pop("allow_redirects", None)
        return super().post(*args, **kwargs)

    def put(self, *args, **kwargs):
        # Remove allow_redirects if present to avoid "unexpected keyword argument" errors
        kwargs.pop("allow_redirects", None)
        return super().put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        # Remove allow_redirects if present to avoid "unexpected keyword argument" errors
        kwargs.pop("allow_redirects", None)
        return super().patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Remove allow_redirects if present to avoid "unexpected keyword argument" errors
        kwargs.pop("allow_redirects", None)
        return super().delete(*args, **kwargs)


@pytest.fixture(scope="session")
def client(app):
    """TestClient fixture with allow_redirects compatibility shim."""
    return TestClient(app)

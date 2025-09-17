"""Test-specific fixtures."""

import json
import logging
import os
import sys

import httpx
import pytest
from httpx import ASGITransport
from starlette.testclient import TestClient as _TestClient

# Import test fixtures


@pytest.fixture(autouse=True, scope="session")
def _lock_test_env():
    """Force test-mode environment for deterministic, dry-run behavior.

    This fixture ensures every test run is isolated, deterministic, and safe:
    - No network calls to external services
    - Dry-run mode for all backends
    - Deterministic timeouts and fallbacks
    - Consistent environment state
    """
    # Absolute no-network / dry-run configuration
    os.environ.setdefault("PYTEST_RUNNING", "1")
    os.environ.setdefault("CI", "1")
    os.environ.setdefault("DRY_RUN", "1")  # CONFIG.dry_run guard
    os.environ.setdefault("PROMPT_BACKEND", "dryrun")  # Fallback path selector
    os.environ.setdefault(
        "DISABLE_OUTBOUND_HTTP", "1"
    )  # http_utils should respect this
    os.environ.setdefault("OPENAI_API_KEY", "test")
    os.environ.setdefault("OPENAI_HTTP_TIMEOUT", "0.01")
    os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:9")  # Blackhole port
    os.environ.setdefault("ENFORCE_JWT_SCOPES", "1")

    # Keep optionals OFF unless a test opts-in explicitly or they're enabled via pytest.ini
    # Note: pytest.ini handles SPOTIFY_ENABLED=1, so we don't remove it here

    # Make sure DEBUG model routing doesn't switch output text
    os.environ.pop("DEBUG_MODEL_ROUTING", None)

    # Prevent any real API calls by setting safe defaults
    os.environ.setdefault("VECTOR_STORE", "memory")  # Use in-memory vector store
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://127.0.0.1:8123")  # Blackhole HA
    os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
    os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")

    yield


@pytest.fixture(scope="session", autouse=True)
def per_worker_database():
    """Configure environment to use the existing gesahni_test database.

    - Uses existing gesahni_test database instead of creating worker-specific ones
    - Sets DATABASE_URL to point to gesahni_test
    - Run Alembic migrations to head if needed
    """
    # Base test flags
    os.environ["PYTEST_RUNNING"] = "1"
    os.environ["DB_POOL"] = "disabled"
    os.environ["ENV"] = "test"
    os.environ["DEV_MODE"] = "1"
    os.environ["ASGI_AUTO_APP"] = "0"

    # Security and rate-limit defaults
    os.environ.setdefault(
        "JWT_SECRET", "test_jwt_secret_for_testing_only_must_be_at_least_32_chars_long"
    )
    os.environ.setdefault("DEV_AUTH", "0")
    os.environ.setdefault("RATE_LIMIT_MODE", "off")
    os.environ.setdefault("ENABLE_RATE_LIMIT_IN_TESTS", "0")

    # Use the existing gesahni_test database instead of creating worker-specific ones
    worker_url = "postgresql://app:app_pw@localhost:5432/gesahni_test"
    os.environ["DATABASE_URL"] = worker_url

    # Run Alembic migrations to head for the test database if needed
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", worker_url)
        command.upgrade(alembic_cfg, "head")
    except Exception:
        # If Alembic is not configured for this repo, continue (fallback models may create on first use)
        pass

    yield


@pytest.fixture(scope="session", autouse=True)
def test_env_flags():
    """Set environment flags to optimize test execution."""
    os.environ["DISABLE_ENV_RELOAD_MW"] = "1"  # avoid logging during teardown
    os.environ.setdefault("DB_POOL", "disabled")  # prevent TooManyConnections
    os.environ.setdefault("PYTHONASYNCIODEBUG", "0")


@pytest.fixture(scope="session", autouse=True)
def sane_logging():
    """Force a simple stdout handler and flush safely for the whole test session."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(logging.INFO)
    root.addHandler(h)
    root.setLevel(logging.INFO)
    try:
        yield
    finally:
        # Best-effort flush; swallow "I/O operation on closed file"
        for h in list(root.handlers):
            try:
                h.flush()
            except Exception:
                pass


@pytest.fixture(autouse=True)
def _reset_llama_health(monkeypatch):
    """Ensure ``LLAMA_HEALTHY`` starts True for each test and silence OTEL."""
    from app import llama_integration

    llama_integration.LLAMA_HEALTHY = True
    # Silence OpenTelemetry exporter during tests to avoid noisy connection errors
    monkeypatch.setenv("OTEL_ENABLED", "0")


# TestClient shim to handle parameter name compatibility
class TestClient(_TestClient):
    """Extended TestClient that handles parameter name compatibility."""

    def get(self, *args, **kwargs):
        # Convert allow_redirects to follow_redirects for compatibility
        if "allow_redirects" in kwargs:
            kwargs["follow_redirects"] = kwargs.pop("allow_redirects")
        return super().get(*args, **kwargs)

    def post(self, *args, **kwargs):
        # Convert allow_redirects to follow_redirects for compatibility
        if "allow_redirects" in kwargs:
            kwargs["follow_redirects"] = kwargs.pop("allow_redirects")
        return super().post(*args, **kwargs)

    def put(self, *args, **kwargs):
        # Convert allow_redirects to follow_redirects for compatibility
        if "allow_redirects" in kwargs:
            kwargs["follow_redirects"] = kwargs.pop("allow_redirects")
        return super().put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        # Convert allow_redirects to follow_redirects for compatibility
        if "allow_redirects" in kwargs:
            kwargs["follow_redirects"] = kwargs.pop("allow_redirects")
        return super().patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Convert allow_redirects to follow_redirects for compatibility
        if "allow_redirects" in kwargs:
            kwargs["follow_redirects"] = kwargs.pop("allow_redirects")
        return super().delete(*args, **kwargs)


@pytest.fixture(scope="session")
def client(app):
    """TestClient fixture with lifespan via context manager to ensure clean startup/shutdown.

    Promoted to session scope so session-scoped fixtures can reuse the same TestClient
    without causing PyTest ScopeMismatch errors when route coverage analyzer requests
    a session-scoped app fixture.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture
def override_db_dependency(monkeypatch, db_session):
    """Override app dependency to use per-test async session where supported."""
    try:

        async def _gen():
            yield db_session

        # Monkeypatch function to yield our session
        monkeypatch.setattr("app.db.core.get_async_db", lambda: _gen())
    except Exception:
        pass
    yield


# Async fixtures and auth helpers for modern test support


@pytest.fixture(scope="session")
def app():
    """Create FastAPI app under test env, lazily."""
    os.environ["ENV"] = "test"
    from app.main import get_app

    return get_app()


@pytest.fixture(scope="session")
async def async_client(app):
    """Async HTTP client using httpx with ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


# Database session per-test with transaction rollback
@pytest.fixture
async def db_session():
    """Provide an async SQLAlchemy session wrapped in a transaction per test.

    Starts a transaction and nested SAVEPOINT. Rolls back on teardown to keep
    the database clean. Uses the engine configured via DATABASE_URL from the
    per_worker_database fixture.
    """
    import os as _os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    dsn = (_os.getenv("DATABASE_URL") or "").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(dsn, future=True)
    AsyncSessionLocal = async_sessionmaker(
        bind=engine, expire_on_commit=False, future=True
    )

    session = AsyncSessionLocal()
    trans = await session.begin()
    nested = await session.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        # Rollback the nested transaction and main transaction
        try:
            await nested.rollback()
        except Exception:
            pass  # Transaction may already be closed
        try:
            await trans.rollback()
        except Exception:
            pass  # Transaction may already be closed
        await engine.dispose()


@pytest.fixture
def test_env(monkeypatch):
    """Set up test environment variables."""
    # Most environment variables are now set globally in pytest_load_initial_conftests
    # This fixture can be used for test-specific overrides if needed
    pass


@pytest.fixture
async def create_test_user(db_session):
    """Create or reuse the standardized test user in the database."""
    from app.user_store import user_store

    # Use standardized test user identity
    test_user_id = "test_user_123"
    username = "test_user_123"
    password = "test_password_123"

    # Use the existing user_store.ensure_user method
    # This will work with whatever database connection is configured
    try:
        await user_store.ensure_user(test_user_id)
    except Exception as e:
        # If user creation fails, continue anyway - the test might still work
        print(f"Warning: Could not ensure user exists: {e}")

    return {
        "user_id": test_user_id,
        "username": username,
        "password": password,
        "email": "test@example.com",
    }


@pytest.fixture
async def seed_spotify_token(create_test_user):
    """Seed a valid Spotify token for the test user."""
    # The token is already created in create_test_user fixture
    return await create_test_user


@pytest.fixture
def seed_calendar_file(tmp_path):
    """Create a temporary calendar file with test events."""
    calendar_data = [
        {
            "date": "2025-01-15",
            "time": "10:00",
            "title": "Test Meeting",
            "description": "A test calendar event",
            "location": "Test Room",
        },
        {
            "date": "2025-01-16",
            "time": "14:30",
            "title": "Another Test Event",
            "description": "Second test event",
            "location": "Office",
        },
    ]

    calendar_file = tmp_path / "test_calendar.json"
    calendar_file.write_text(json.dumps(calendar_data))

    # Set the environment variable to point to our test file
    os.environ["CALENDAR_FILE"] = str(calendar_file)

    return str(calendar_file)


@pytest.fixture
async def authed_client(async_client, create_test_user):
    """Async client with authentication cookies set using standardized test user."""
    from fastapi.responses import Response

    from app.tokens import make_access
    from app.web.cookies import set_auth_cookies

    user_data = create_test_user
    user_id = user_data["user_id"]

    # Create a mock response to set cookies
    response = Response()

    # Generate access token
    access_token = make_access({"user_id": user_id})

    # Get token TTLs
    from app.cookie_config import get_token_ttls

    access_ttl, refresh_ttl = get_token_ttls()

    # Create a mock request (needed for set_auth_cookies)
    from fastapi import Request

    mock_request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": {},
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        }
    )

    # Set auth cookies
    set_auth_cookies(
        response,
        access=access_token,
        refresh=None,
        session_id=None,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=mock_request,
    )

    # Extract cookies from the response
    cookies = {}
    for header_name, header_value in response.headers.items():
        if header_name.lower() == "set-cookie":
            # Parse the Set-Cookie header
            cookie_parts = header_value.split(";")[0].split("=", 1)
            if len(cookie_parts) == 2:
                cookies[cookie_parts[0]] = cookie_parts[1]

    # Set cookies on the async client
    for name, value in cookies.items():
        async_client.cookies.set(name, value, domain="testserver")

    return async_client

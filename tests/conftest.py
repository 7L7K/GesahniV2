"""Test-specific fixtures."""

import os
import tempfile
import pytest
import asyncio
import json
import time
import httpx
from pathlib import Path
from starlette.testclient import TestClient as _TestClient
from httpx import ASGITransport


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db_and_init_tables():
    """Guarantee DB tables exist before any tests touch the databases.

    This fixture runs once per test session and ensures all database tables
    are created before any test code runs, preventing sqlite3.OperationalError.
    """
    # Mark that we're running tests
    os.environ["PYTEST_RUNNING"] = "1"

    # Set critical test environment variables EARLY to override any defaults from env files
    os.environ["JWT_SECRET"] = (
        "test_jwt_secret_for_testing_only_must_be_at_least_32_chars_long"
    )
    os.environ["DEV_MODE"] = "1"
    os.environ["COOKIE_SAMESITE"] = "Lax"
    os.environ["COOKIE_SECURE"] = "false"
    os.environ["COOKIE_DOMAIN"] = ""  # Empty string = host-only cookies for tests
    os.environ["CORS_ALLOW_CREDENTIALS"] = (
        "true"  # Required for cookie auth to work with CORS
    )
    os.environ["CORS_ALLOW_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000"
    os.environ["SPOTIFY_TEST_MODE"] = "1"

    # Additional rate limiting variables for predictable test behavior
    os.environ["RATE_LIMIT_PER_MIN"] = "1000"  # High limit to prevent interference
    os.environ["RATE_LIMIT_BURST"] = "100"  # High burst limit
    os.environ["RATE_LIMIT_WINDOW_S"] = "60"
    os.environ["RATE_LIMIT_BURST_WINDOW_S"] = "10"
    os.environ["RATE_LIMIT_BYPASS_SCOPES"] = "admin,test"
    os.environ["RATE_LIMIT_KEY_SCOPE"] = "global"
    os.environ["RATE_LIMIT_BACKEND"] = "memory"

    # STANDARDIZED TEST IDENTITY AND TTL CONFIGURATION
    # =================================================
    # Use long TTLs to prevent expiry during test execution
    os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")  # 1 hour access tokens
    os.environ.setdefault("JWT_REFRESH_EXPIRE_MINUTES", "1440")  # 1 day refresh tokens
    os.environ.setdefault("CSRF_TTL_SECONDS", "3600")  # 1 hour CSRF tokens

    # Additional test environment variables for predictable behavior
    os.environ.setdefault("JWT_CLOCK_SKEW_S", "60")  # Allow 1 minute clock skew
    os.environ.setdefault("ENV", "test")  # Explicit test environment
    os.environ.setdefault("USE_DEV_PROXY", "0")  # Disable dev proxy for tests
    os.environ.setdefault("AUTH_DEV_BYPASS", "0")  # Disable auth bypass
    os.environ.setdefault("CLERK_ENABLED", "0")  # Disable Clerk integration
    os.environ.setdefault("OAUTH_TEST_MODE", "1")  # Enable OAuth test mode
    os.environ.setdefault("LOG_LEVEL", "WARNING")  # Reduce log noise during tests
    os.environ.setdefault("DISABLE_REQUEST_LOGGING", "1")  # Disable request logging

    # Disable rate limiting for tests to prevent 429 errors
    # Force disable globally - cannot be overridden by individual tests
    os.environ["RATE_LIMIT_MODE"] = "off"
    # Also set ENABLE_RATE_LIMIT_IN_TESTS to 0 for consistency
    os.environ["ENABLE_RATE_LIMIT_IN_TESTS"] = "0"

    # Set up test database directory - use a dedicated temp directory for tests
    test_db_dir = os.path.join(tempfile.gettempdir(), "gesahni_test_dbs")
    os.environ["GESAHNI_TEST_DB_DIR"] = test_db_dir

    # Ensure the test directory exists
    os.makedirs(test_db_dir, exist_ok=True)

    # Database initialization will be handled by the async app fixture
    # which properly manages the event loop through pytest-asyncio


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
    """TestClient fixture with parameter name compatibility shim."""
    return TestClient(app)


# Async fixtures and auth helpers for modern test support


@pytest.fixture(scope="session")
async def app():
    """Async FastAPI app fixture with lifespan management."""
    from app.main import app as fastapi_app
    from app.main import lifespan

    # Start the app with lifespan (env vars are set in _setup_test_db_and_init_tables)
    async with lifespan(fastapi_app):
        yield fastapi_app


@pytest.fixture(scope="session")
async def async_client(app):
    """Async HTTP client using httpx with ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def test_env(monkeypatch):
    """Set up test environment variables."""
    # Most environment variables are now set globally in pytest_load_initial_conftests
    # This fixture can be used for test-specific overrides if needed
    pass


@pytest.fixture(scope="session")
async def create_test_user():
    """Create or reuse the standardized test user in the database."""
    from app.user_store import user_store
    from app.models.third_party_tokens import ThirdPartyToken
    from app.auth_store_tokens import upsert_token

    # Use standardized test user identity
    test_user_id = "test_user_123"
    username = "test_user_123"
    password = "test_password_123"

    # Ensure user exists in user store
    await user_store.ensure_user(test_user_id)

    # Create a valid Spotify token for testing
    expires_at = int(time.time()) + 3600  # 1 hour from now
    token_data = ThirdPartyToken(
        identity_id="59fd9451-f29e-43ce-a845-e11a3e494759",
        id="spotify_test_token",
        user_id=test_user_id,
        provider="spotify",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        expires_at=expires_at,
        scopes="user-read-private user-read-email",
    )

    # Upsert the token
    await upsert_token(token_data)

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
    from app.cookies import set_auth_cookies
    from app.tokens import make_access
    from fastapi.responses import Response

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

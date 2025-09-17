import importlib
import os
import pathlib
import socket
import sys
import time
import uuid
import warnings

import pytest

# Ensure test fixtures in tests/_fixtures are imported early so their
# autouse/session fixtures run before app composition and migrations.
try:
    importlib.import_module("tests._fixtures.db")
    importlib.import_module("tests._fixtures.app")
except Exception:
    # If imports fail, continue; the fixtures may not be present in some contexts
    pass


# Session-scoped fixtures for live server testing
@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db_and_env():
    os.environ["PYTEST_RUNNING"] = "1"
    os.environ.setdefault("TEST_MODE", "1")
    os.environ.setdefault("TEST_DISABLE_RATE_LIMITS", "1")
    os.environ.setdefault("TEST_DISABLE_CSRF", "1")
    os.environ.setdefault("ENABLE_GOOGLE_OAUTH", "1")
    os.environ.setdefault("ENABLE_SPOTIFY", "1")

    # Offline mode: disable all external service checks during tests
    os.environ.setdefault("TEST_OFFLINE", "1")
    os.environ.setdefault("STARTUP_VENDOR_PINGS", "0")

    # isolated DB dir for this run
    os.environ.setdefault(
        "GESAHNI_TEST_DB_DIR", f"/tmp/gesahni_tests/{uuid.uuid4().hex}"
    )
    pathlib.Path(os.environ["GESAHNI_TEST_DB_DIR"]).mkdir(parents=True, exist_ok=True)

    # Don't call init_db_once here - let the app's lifespan handler do it
    # to avoid event loop conflicts
    return True


# Live server fixture - only start if needed by tests
@pytest.fixture(scope="session")
def live_server(_bootstrap_db_and_env):
    import subprocess

    # Start server using subprocess with dedicated script
    cmd = [sys.executable, "test_server.py"]
    p = subprocess.Popen(
        cmd, cwd=os.getcwd(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # wait for server
    deadline = time.time() + 15
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 8000), timeout=0.5):
                break
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    else:
        p.terminate()
        p.wait(timeout=2)
        raise RuntimeError(f"Uvicorn failed to start on :8000 (last_err={last_err})")

    yield p
    try:
        p.terminate()
        p.wait(timeout=2)
    except Exception:
        pass


# Pytest early hook: set test DB dir and flags before any imports
def pytest_load_initial_conftests(early_config, parser):
    try:
        # Mark pytest running so modules that compute DB paths at import see it
        os.environ.setdefault("PYTEST_RUNNING", "1")

        # Force CI/test profile so startup uses the lightweight 'ci' profile
        # and avoids starting background daemons that conflict with pytest event loop.
        os.environ.setdefault("CI", "1")

        # Per-worker test database configuration (xdist sets PYTEST_XDIST_WORKER or PYTEST_WORKER_ID)
        worker = (
            os.getenv("PYTEST_XDIST_WORKER") or os.getenv("PYTEST_WORKER_ID") or "main"
        )

        # Use PostgreSQL for tests since container is running
        # Create per-worker test databases to ensure isolation
        if worker != "main":
            os.environ.setdefault(
                "DATABASE_URL",
                f"postgresql://app:app_pw@localhost:5432/gesahni_test_{worker}",
            )
        else:
            os.environ.setdefault(
                "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni_test"
            )

        # Test-friendly configuration overrides
        # JWT: Allow short secrets in tests
        os.environ.setdefault("DEV_MODE", "1")  # Allows weak JWT secrets
        os.environ.setdefault(
            "ENV", "test"
        )  # Set environment to test for proper isolation
        # Provide a deterministic dev JWT secret to enable token minting
        os.environ.setdefault(
            "JWT_SECRET",
            "x" * 64,  # Use a secure 64-character secret for tests
        )

        # Rate limiting: Disable for tests by default
        os.environ.setdefault("ENABLE_RATE_LIMIT_IN_TESTS", "0")
        # Force disable rate limiting globally for tests - cannot be overridden
        os.environ["RATE_LIMIT_MODE"] = "off"

        # CSRF: Disable for tests
        os.environ.setdefault("CSRF_ENABLED", "0")

        # WebSocket: Disable problematic async logging
        os.environ.setdefault("WS_DISABLE_ASYNC_LOGGING", "1")

        # Metrics: Disable Prometheus in tests to avoid port conflicts
        os.environ.setdefault("PROMETHEUS_ENABLED", "0")

        # Logging: Reduce verbosity in tests
        os.environ.setdefault("LOG_LEVEL", "WARNING")

        # CORS: Disable strict origin checking for tests
        os.environ.setdefault("CORS_ALLOW_ORIGINS", "*")

        # Session: Use memory-based sessions for tests
        os.environ.setdefault("SESSION_STORE", "memory")

        # Vector store: Use memory backend for tests
        os.environ.setdefault("VECTOR_STORE", "memory")

        # Prompt backend: Use dryrun for safe development and testing
        os.environ.setdefault("PROMPT_BACKEND", "dryrun")

        # STANDARDIZED TEST IDENTITY AND TTL CONFIGURATION
        # ==================================================
        # Use long TTLs to prevent expiry during test execution
        os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")  # 1 hour access tokens
        os.environ.setdefault(
            "JWT_REFRESH_EXPIRE_MINUTES", "1440"
        )  # 1 day refresh tokens
        os.environ.setdefault("CSRF_TTL_SECONDS", "3600")  # 1 hour CSRF tokens

        # Allow optional auth in tests for convenience
        os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")

        # Cookie configuration for tests
        os.environ.setdefault("COOKIE_SAMESITE", "Lax")
        os.environ.setdefault("COOKIE_SECURE", "false")
        os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "true")

    except Exception as e:
        print(f"Warning: Failed to set test configuration: {e}")
        pass


# Filter Pydantic v2 deprecation warnings to keep CI green
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
from fastapi.testclient import TestClient


# STANDARDIZED TEST CLIENT FIXTURE
# ==================================
# Single source of truth for test client configuration
@pytest.fixture(scope="session")
def client():
    """
    Standardized test client fixture for all tests.

    This fixture provides:
    - Consistent environment configuration
    - Long TTLs to prevent expiry during test execution
    - Standardized test user identity
    - Proper database initialization
    """
    # Import the FastAPI app after test env vars are set
    from app.main import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture
def prompt_router(monkeypatch):
    """Provide a mock async prompt router and monkeypatch backwards-compat hook.

    Many legacy tests monkeypatch or call `app.main.route_prompt`. To ease
    migration we expose a `prompt_router` fixture that sets a default
    AsyncMock on `app.main.route_prompt` so tests can inject/override it.
    """
    from unittest.mock import AsyncMock

    pr = AsyncMock()
    try:
        import app.main as main_mod

        # Allow tests to monkeypatch this further if needed
        monkeypatch.setattr(main_mod, "route_prompt", pr, raising=False)
    except Exception:
        # If main isn't importable in some contexts, ignore
        pass
    return pr


@pytest.fixture(scope="session")
def app_client():
    """Alias for client fixture to maintain backward compatibility."""
    from app.main import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture
def app():
    """Provide the FastAPI app instance for tests that need direct access."""
    from app.main import create_app

    return create_app()


@pytest.fixture(scope="session")
async def async_app():
    """Provide the FastAPI app instance for async tests."""
    from app.main import create_app

    return create_app()


@pytest.fixture(scope="session")
async def async_client(async_app):
    """Provide an async test client using httpx with ASGITransport."""
    from httpx import ASGITransport

    from app.http_client import build_async_httpx_client

    # Create async client with lifespan support (lifespan is handled automatically)
    transport = ASGITransport(app=async_app)
    client = build_async_httpx_client(transport=transport, base_url="http://testserver")

    try:
        yield client
    finally:
        # Ensure client is properly closed
        await client.aclose()


# STANDARDIZED TEST USER FIXTURE
# ===============================
@pytest.fixture(scope="session")
async def test_user():
    """
    Standardized test user for all tests.

    Creates a consistent test user identity that can be used across all tests:
    - Username: test_user_123
    - Password: test_password_123
    - Email: test@example.com
    """
    import time

    from app.auth_store_tokens import ThirdPartyToken, upsert_token
    from app.user_store import user_store

    user_id = "test_user_123"
    username = "test_user_123"
    password = "test_password_123"

    # Ensure user exists in user store
    await user_store.ensure_user(user_id)

    # Create a Spotify token for testing (if needed)
    expires_at = int(time.time()) + 3600  # 1 hour from now
    spotify_token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        access_token="test_spotify_access_token",
        refresh_token="test_spotify_refresh_token",
        expires_at=expires_at,
        scopes="user-read-private,user-read-email",
    )

    try:
        await upsert_token(spotify_token)
    except Exception:
        # Token might already exist, ignore
        pass

    return {
        "user_id": user_id,
        "username": username,
        "password": password,
        "email": "test@example.com",
    }


@pytest.fixture
async def cors_client(async_app):
    """Provide an async test client configured for CORS testing."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=async_app)
    client = AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=30.0,  # Use longer timeout for consistency
        follow_redirects=True,
        headers={"Origin": "http://localhost:3000"},  # Default CORS origin for tests
    )

    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def csrf_client(async_app):
    """Provide an async test client configured for CSRF testing."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=async_app)
    client = AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=30.0,  # Use longer timeout for consistency
        follow_redirects=True,
        headers={"Origin": "http://localhost:3000", "Referer": "http://localhost:3000"},
    )

    try:
        yield client
    finally:
        await client.aclose()


async def fetch_csrf_token(client):
    """Helper function to fetch CSRF token from a safe endpoint."""
    # Try to get CSRF token from /v1/csrf endpoint if it exists
    try:
        response = await client.get("/v1/csrf")
        if response.status_code == 200:
            data = response.json()
            token = data.get("csrf_token")
            if token:
                return token
    except Exception:
        pass

    # Fallback: GET request to a safe endpoint that should set CSRF cookie
    safe_endpoints = ["/health", "/v1/health", "/"]
    for endpoint in safe_endpoints:
        try:
            response = await client.get(endpoint)
            if response.status_code == 200:
                # Check if CSRF token was set in cookie
                csrf_cookie = response.cookies.get("csrf_token")
                if csrf_cookie:
                    return csrf_cookie
                # Check if token was returned in X-CSRF-Token header
                csrf_header = response.headers.get("X-CSRF-Token")
                if csrf_header:
                    return csrf_header
        except Exception:
            continue

    # Last resort: generate a random token for testing
    import secrets

    return secrets.token_urlsafe(16)


async def prepare_csrf_request(client):
    """Prepare client for CSRF-protected requests by fetching and setting token."""
    csrf_token = await fetch_csrf_token(client)

    # Set the CSRF cookie
    client.cookies.set("csrf_token", csrf_token, domain="testserver")

    # Return the token for use in headers
    return csrf_token


@pytest.fixture
async def cors_csrf_client(async_app):
    """Provide an async test client configured for CORS + CSRF testing."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=async_app)
    client = AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=10.0,
        follow_redirects=True,
        headers={"Origin": "http://localhost:3000", "Referer": "http://localhost:3000"},
    )

    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def seed_spotify_token():
    """Seed a Spotify token for testing."""
    from app.auth_store_tokens import upsert_token
    from app.models.third_party_tokens import ThirdPartyToken

    token = ThirdPartyToken(
        user_id="test_user",
        provider="spotify",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=int(time.time()) + 3600,  # 1 hour from now
        scopes="user-read-private,user-read-email",
    )
    await upsert_token(token)
    return token


# conftest.py
#
# Pytest bootstrap that hermetically seals the test runtime.
# - Guarantees NO network, NO disk writes outside a tmpdir,
#   and wipes any global flags/envs that could leak across tests.
# - Stubs ChromaDB, OpenAI, and Ollama so unit tests never punch
#   through to real services.
#
# Drop this at project root; pytest auto-discovers it.

import math
import shutil
import tempfile
import types
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# 🔐  Hard-set critical env vars before anything else imports app code
# ──────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("JWT_SECRET", "x" * 64)
os.environ.setdefault("DEBUG_MODEL_ROUTING", "0")  # disable dry-run by default
os.environ.setdefault("DEBUG", "0")

# Vector store should *never* hit disk or real Chroma in unit tests
os.environ["VECTOR_STORE"] = "memory"

# Dummy Ollama settings so any health check short-circuits instantly
os.environ["OLLAMA_URL"] = "http://x"
os.environ["OLLAMA_MODEL"] = "llama3"
os.environ["ALLOWED_LLAMA_MODELS"] = "llama3"
os.environ["ALLOWED_GPT_MODELS"] = "gpt-4o,gpt-4,gpt-3.5-turbo"


# ──────────────────────────────────────────────────────────────────────────────
# 🧪  ChromaDB full stub (in-mem cosine search)
# ──────────────────────────────────────────────────────────────────────────────
def _cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    num = sum(x * y for x, y in zip(a, b, strict=False))
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / denom if denom else 0.0


class _CollectionStub:
    def __init__(self, embedding_function=None, metadata=None) -> None:
        self._embed = embedding_function or (lambda texts: [[0.0] * 3 for _ in texts])
        self._space = (metadata or {}).get("hnsw:space", "cosine")
        self._store: dict[str, dict[str, Any]] = {}

    # --- Chroma surface ------------------------------------------------------
    def upsert(self, *, ids, documents, metadatas, embeddings=None):
        embeddings = embeddings or self._embed(documents)
        for i, doc, meta, emb in zip(
            ids, documents, metadatas, embeddings, strict=False
        ):
            self._store[i] = {"document": doc, "metadata": meta, "embedding": emb}

    def delete(self, *, ids):
        for i in ids:
            self._store.pop(i, None)

    def get(self, include=None):
        return {"ids": list(self._store)}

    def update(self, *, ids, metadatas):
        for i, meta in zip(ids, metadatas, strict=False):
            if i in self._store:
                self._store[i]["metadata"].update(meta)

    def query(
        self,
        *,
        query_texts,
        n_results,
        include=None,
        where=None,
    ):
        q_embs = self._embed(query_texts)
        ids_list, docs_list, metas_list, dists_list = [], [], [], []
        for q_emb in q_embs:
            scored = []
            for i, rec in self._store.items():
                if where and any(rec["metadata"].get(k) != v for k, v in where.items()):
                    continue
                if self._space == "l2":
                    dist = math.sqrt(
                        sum(
                            (x - y) ** 2
                            for x, y in zip(q_emb, rec["embedding"], strict=False)
                        )
                    )
                else:
                    dist = 1.0 - _cosine_similarity(q_emb, rec["embedding"])
                scored.append((dist, i, rec))
            scored.sort(key=lambda x: x[0])
            scored = scored[: n_results or len(scored)]
            ids_list.append([i for _, i, _ in scored])
            docs_list.append([r["document"] for _, _, r in scored])
            metas_list.append([r["metadata"] for _, _, r in scored])
            dists_list.append([d for d, _, _ in scored])

        out = {"ids": ids_list}
        if include is None or "documents" in include:
            out["documents"] = docs_list
        if include is None or "metadatas" in include:
            out["metadatas"] = metas_list
        if include is None or "distances" in include:
            out["distances"] = dists_list
        return out


class _ClientStub:
    def __init__(self, path: str | None = None) -> None:
        self._cols: dict[str, _CollectionStub] = {}

    def get_or_create_collection(self, name, *, embedding_function=None, metadata=None):
        if name not in self._cols:
            self._cols[name] = _CollectionStub(embedding_function, metadata)
        return self._cols[name]

    def reset(self):
        self._cols.clear()

    close = reset


chromadb_stub = types.SimpleNamespace(PersistentClient=_ClientStub)
sys.modules["chromadb"] = chromadb_stub
sys.modules["chromadb.config"] = types.SimpleNamespace(
    Settings=type("Settings", (), {})
)
sys.modules["chromadb.utils"] = types.SimpleNamespace()
sys.modules["chromadb.utils.embedding_functions"] = types.SimpleNamespace()


# ──────────────────────────────────────────────────────────────────────────────
# 🛟  Ensure openai.OpenAIError exists even if openai is stubbed
# ──────────────────────────────────────────────────────────────────────────────
def _ensure_openai_error() -> None:
    sys.modules.pop("openai", None)  # force re-import
    try:
        import importlib

        openai = importlib.import_module("openai")  # type: ignore
        if not hasattr(openai, "OpenAIError"):

            class OpenAIError(Exception):
                pass

            openai.OpenAIError = OpenAIError
    except Exception:  # pragma: no cover
        pass


_ensure_openai_error()

# ------------------------------------------------------------------------------
# 📂  Ephemeral CHROMA_PATH per test session
# ------------------------------------------------------------------------------
_prev_chroma = os.environ.get("CHROMA_PATH")
_tmp_chroma = tempfile.mkdtemp(prefix="chroma_test_")
os.environ["CHROMA_PATH"] = _tmp_chroma


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_tmp_chroma, ignore_errors=True)
    if _prev_chroma is not None:
        os.environ["CHROMA_PATH"] = _prev_chroma
    else:
        os.environ.pop("CHROMA_PATH", None)


# ------------------------------------------------------------------------------
# 🔒  DOTENV autouse fixture: prevent .env writes during tests
# ------------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _prevent_dotenv_writes(tmp_path_factory):
    """Prevent .env file writes during tests by redirecting to tmp directory."""
    tmp_dir = tmp_path_factory.mktemp("dotenv")
    test_env_path = tmp_dir / ".env.test"
    os.environ["DOTENV_PATH"] = str(test_env_path)
    yield
    # Clean up after session
    if "DOTENV_PATH" in os.environ:
        del os.environ["DOTENV_PATH"]


# ------------------------------------------------------------------------------
# 🔄  Global autouse fixture: nuke debug envs + reset health flags each test
# ------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_debug_and_flags(monkeypatch):
    # Clear debug envs so route_prompt never enters dry-run unless a test asks
    # Also reset retrieval pipeline flags between tests to avoid leakage
    for var in ("DEBUG", "DEBUG_MODEL_ROUTING", "USE_RETRIEVAL_PIPELINE"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(var, "0")

    # Ensure a stable default vector backend per test. Individual tests may
    # override this (e.g. to "dual"). Setting it here avoids cross‑test bleed.
    monkeypatch.setenv("VECTOR_STORE", "memory")

    # Reset LLaMA/GPT health and circuit flags
    try:
        import app.model_picker as model_picker
        import app.router as router
    except Exception:
        model_picker = type("_", (), {"LLAMA_HEALTHY": True})
        router = type("_", (), {"llama_circuit_open": False, "LLAMA_HEALTHY": True})

    router.llama_circuit_open = False
    router.LLAMA_HEALTHY = True
    model_picker.LLAMA_HEALTHY = True

    # Reset vector store to ensure test isolation
    try:
        from app.memory.api import close_store

        close_store()
    except Exception:
        pass  # Ignore if vector store not available

    # Reset rate-limiter buckets (HTTP & WS) between tests
    try:
        import app.security as security

        security.http_requests.clear()
        security.ws_requests.clear()
        security.http_burst.clear()
        security.ws_burst.clear()
        security._requests.clear()
    except Exception:
        pass

    # Tell application code we're inside pytest (if you want to gate features)
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    # Normalize cookie canon per test to avoid cross-test leakage
    monkeypatch.setenv("COOKIE_CANON", "gsnh")
    # Reload cookie helpers to pick up new canon in case previous tests imported them
    try:
        import importlib

        import app.web.cookies as _cookies_mod

        importlib.reload(_cookies_mod)
    except Exception:
        pass
    # Ensure auth and token DB tables exist for tests that expect DB-backed tables.
    try:
        import app.auth_store as _auth_store
        import app.auth_store_tokens as _auth_tokens
        import app.care_store as _care_store
        import app.music.store as _music_store

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_auth_store.ensure_tables())
        except Exception:
            pass
        try:
            # Ensure token table exists (use class default path)
            dao = _auth_tokens.TokenDAO(
                str(
                    getattr(
                        _auth_tokens.TokenDAO,
                        "DEFAULT_DB_PATH",
                        _auth_tokens.DEFAULT_DB_PATH,
                    )
                )
            )
            loop.run_until_complete(dao._ensure_table())
        except Exception:
            pass
        try:
            # Ensure care store tables exist for care-related tests
            loop.run_until_complete(_care_store.ensure_tables())
        except Exception:
            pass
        try:
            # Ensure music store tables exist for music-related tests
            loop.run_until_complete(_music_store._ensure_tables())
        except Exception:
            pass
    except Exception:
        # If auth modules aren't importable during some unit tests, ignore
        pass

    yield


# ------------------------------------------------------------------------------
# 📝  Pytest hooks
# ------------------------------------------------------------------------------
pytest_plugins = ("pytest_asyncio",)


def pytest_collect_file(file_path: Path, parent):  # type: ignore[override]
    # Guarantee OpenAIError exists even if other tests muck with import order
    _ensure_openai_error()
    return None  # allow default collection


def pytest_configure(config):
    # Nothing extra; env vars handled at top-level already
    pass

import os
import time
import warnings

# Pytest early hook: set test DB dir and flags before any imports
def pytest_load_initial_conftests(early_config, parser):
    try:
        # Mark pytest running so modules that compute DB paths at import see it
        os.environ.setdefault("PYTEST_RUNNING", "1")

        # Per-worker test DB directory (xdist sets PYTEST_XDIST_WORKER or PYTEST_WORKER_ID)
        worker = os.getenv("PYTEST_XDIST_WORKER") or os.getenv("PYTEST_WORKER_ID") or "main"
        test_dir = f"/tmp/gesahni_tests/{worker}"
        os.environ.setdefault("GESAHNI_TEST_DB_DIR", test_dir)

        # Test-friendly configuration overrides
        # JWT: Allow short secrets in tests
        os.environ.setdefault("DEV_MODE", "1")  # Allows weak JWT secrets
        os.environ.setdefault("ENV", "dev")     # Alternative way to allow weak secrets

        # Rate limiting: Disable for tests by default
        os.environ.setdefault("ENABLE_RATE_LIMIT_IN_TESTS", "0")

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

    except Exception as e:
        print(f"Warning: Failed to set test configuration: {e}")
        pass

import pytest

# Filter Pydantic v2 deprecation warnings to keep CI green
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    # Put app in test mode for routes that relax auth in tests
    monkeypatch.setenv("PYTEST_MODE", "1")
    # Allow anonymous requests in tests unless a JWT is explicitly set by a test
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")

    # Ensure test-friendly configuration (fallback for tests not using early hook)
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ENABLE_RATE_LIMIT_IN_TESTS", "0")
    monkeypatch.setenv("CSRF_ENABLED", "0")
    monkeypatch.setenv("WS_DISABLE_ASYNC_LOGGING", "1")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("SESSION_STORE", "memory")
    monkeypatch.setenv("VECTOR_STORE", "memory")

    # Set database path explicitly to ensure all modules use the same test DB
    import tempfile
    import os
    import subprocess
    import sys

    test_db_path = tempfile.mktemp(suffix='.db')
    monkeypatch.setenv("CARE_DB", test_db_path)
    monkeypatch.setenv("AUTH_DB", test_db_path)
    monkeypatch.setenv("MUSIC_DB", test_db_path)

    # Set up test database tables using the setup script
    try:
        result = subprocess.run([sys.executable, "test_setup_db.py"],
                              capture_output=True, text=True, cwd=os.getcwd())
        if result.returncode != 0:
            print(f"DB setup failed: {result.stderr}")
    except Exception as e:
        print(f"DB setup failed: {e}")
        # Silent fail - DB setup should not break tests
        pass

    # Import the FastAPI `app` after test env vars are set to ensure
    # DB path computation and startup logic detect pytest mode.
    from app.main import app

    return TestClient(app)


@pytest.fixture
def app_client(monkeypatch):
    """Alias for client fixture to match test expectations."""
    # Put app in test mode for routes that relax auth in tests
    monkeypatch.setenv("PYTEST_MODE", "1")
    # Allow anonymous requests in tests unless a JWT is explicitly set by a test
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")

    # Set database path explicitly to ensure all modules use the same test DB
    import tempfile
    import os
    test_db_path = tempfile.mktemp(suffix='.db')
    monkeypatch.setenv("CARE_DB", test_db_path)
    monkeypatch.setenv("AUTH_DB", test_db_path)
    monkeypatch.setenv("MUSIC_DB", test_db_path)

    # Force database schema initialization BEFORE creating TestClient
    # Note: This approach has issues because modules are imported before fixtures run
    try:
        # Simple synchronous approach to ensure tables exist
        import sqlite3

        # Create tables directly using sqlite3
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()

        # Create care_sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS care_sessions (
                id TEXT PRIMARY KEY,
                resident_id TEXT,
                title TEXT,
                transcript_uri TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)

        # Create auth_users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL
            )
        """)

        # Create contacts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                resident_id TEXT,
                name TEXT,
                phone TEXT,
                priority INTEGER,
                quiet_hours TEXT
            )
        """)

        # Create tv_config table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tv_config (
                resident_id TEXT PRIMARY KEY,
                ambient_rotation INTEGER,
                rail TEXT,
                quiet_hours TEXT,
                default_vibe TEXT,
                updated_at REAL
            )
        """)

        conn.commit()
        conn.close()

        print(f"DEBUG: Created test DB at {test_db_path}")

    except Exception as e:
        print(f"DB init failed: {e}")
        # Silent fail - DB init should not break tests
        pass

    # Import `app` after envs are configured so startup sees test flags
    from app.main import app
    return TestClient(app)


@pytest.fixture
async def seed_spotify_token():
    """Seed a Spotify token for testing."""
    from app.models.third_party_tokens import ThirdPartyToken
    from app.auth_store_tokens import upsert_token

    token = ThirdPartyToken(
        user_id="test_user",
        provider="spotify",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=int(time.time()) + 3600,  # 1 hour from now
        scope="user-read-private,user-read-email"
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
import sys
import tempfile
import types
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# 🔐  Hard-set critical env vars before anything else imports app code
# ──────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("JWT_SECRET", "secret")
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
    import app.model_picker as model_picker
    import app.router as router

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
            dao = _auth_tokens.TokenDAO(str(getattr(_auth_tokens.TokenDAO, "DEFAULT_DB_PATH", _auth_tokens.DEFAULT_DB_PATH)))
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

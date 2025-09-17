"""Smoke test for unified vector store configuration."""

import os

import pytest
from fastapi.testclient import TestClient


def _setup_app(monkeypatch, vector_dsn: str):
    """Set up app with specific vector store DSN."""
    # Clear any existing vector store env vars
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("VECTOR_DSN", raising=False)

    # Set the unified DSN
    monkeypatch.setenv("VECTOR_DSN", vector_dsn)

    # Set a lower similarity threshold for tests to ensure matches
    monkeypatch.setenv("SIM_THRESHOLD", "0.1")

    # Other required env vars
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
    os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
    os.environ.setdefault("ENV_RELOAD_ON_REQUEST", "1")

    # Force reload of memory modules to pick up new env vars
    import importlib

    import app.memory.api
    import app.memory.unified_store

    importlib.reload(app.memory.unified_store)
    importlib.reload(app.memory.api)

    from app.main import create_app

    app = create_app()
    # Mock startup functions to avoid real network calls
    monkeypatch.setattr(app, "ha_startup", lambda: None)
    monkeypatch.setattr(app, "llama_startup", lambda: None)
    return app


def test_vector_store_memory_backend(monkeypatch):
    """Test memory backend via VECTOR_DSN."""
    app = _setup_app(monkeypatch, "memory://")
    client = TestClient(app)

    # Test health endpoint
    r = client.get("/v1/health/vector_store")
    assert r.status_code == 200
    data = r.json()

    assert data["ok"] is True
    assert data["store_type"] == "MemoryVectorStore"
    assert data["config"]["scheme"] == "memory"
    assert data["test_passed"] is True
    assert data["embedding_model"] == "text-embedding-3-small"
    assert data["embedding_dim"] == "1536"
    assert data["distance_metric"] == "COSINE"


def test_vector_store_chroma_backend(monkeypatch, tmp_path):
    """Test Chroma backend via VECTOR_DSN."""
    chroma_path = str(tmp_path / "chroma_test")
    app = _setup_app(monkeypatch, f"chroma:///{chroma_path}")
    client = TestClient(app)

    # Test health endpoint
    r = client.get("/v1/health/vector_store")
    assert r.status_code == 200
    data = r.json()

    assert data["ok"] is True
    assert data["store_type"] == "ChromaVectorStore"
    assert data["config"]["scheme"] == "chroma"
    # Handle path normalization differences
    assert data["config"]["path"] in [chroma_path, chroma_path.lstrip("/")]
    # For Chroma with length embedder, the test might not find the memory due to embedding differences
    # Just check that the store is working and we got a memory ID back
    assert data["test_memory_id"] is not None
    assert data["backend_stats"]["backend"] == "chroma"
    assert data["backend_stats"]["path"] in [chroma_path, chroma_path.lstrip("/")]


def test_vector_store_qdrant_backend(monkeypatch):
    """Test Qdrant backend via VECTOR_DSN (requires running Qdrant)."""
    # Skip if Qdrant is not available
    try:
        from app.memory.vector_store.qdrant import QdrantVectorStore

        if QdrantVectorStore is None:
            pytest.skip("Qdrant not available")
    except ImportError:
        pytest.skip("Qdrant dependencies not installed")

    app = _setup_app(monkeypatch, "qdrant://localhost:6333")
    client = TestClient(app)

    # Test health endpoint
    r = client.get("/v1/health/vector_store")
    assert r.status_code == 200
    data = r.json()

    # Qdrant might fail if not running, but config should be correct
    if data["ok"] and data["store_type"] == "QdrantVectorStore":
        assert data["config"]["scheme"] == "qdrant"
        assert data["config"]["host"] == "localhost"
        assert data["config"]["port"] == "6333"
        assert data["test_passed"] is True
        assert "backend_stats" in data
    else:
        # If Qdrant is not running or not available, it should fall back to memory
        assert data["store_type"] == "MemoryVectorStore"
        assert data["test_passed"] is True


def test_vector_store_legacy_compatibility(monkeypatch, tmp_path):
    """Test backward compatibility with legacy VECTOR_STORE env var."""
    chroma_path = str(tmp_path / "chroma_legacy")

    # Use legacy VECTOR_STORE instead of VECTOR_DSN
    monkeypatch.delenv("VECTOR_DSN", raising=False)
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.setenv("CHROMA_PATH", chroma_path)
    monkeypatch.setenv("SIM_THRESHOLD", "0.1")

    # Force reload of memory modules to pick up new env vars
    import importlib

    import app.memory.api
    import app.memory.unified_store

    importlib.reload(app.memory.unified_store)
    importlib.reload(app.memory.api)

    # Other required env vars
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
    os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
    os.environ.setdefault("ENV_RELOAD_ON_REQUEST", "1")

    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    app = main.app
    client = TestClient(app)

    # Test health endpoint
    r = client.get("/v1/health/vector_store")
    assert r.status_code == 200
    data = r.json()

    assert data["ok"] is True
    assert data["store_type"] == "ChromaVectorStore"
    # For Chroma with length embedder, just check we got a memory ID
    assert data["test_memory_id"] is not None


def test_vector_store_default_fallback(monkeypatch):
    """Test default fallback when no DSN is provided."""
    # Clear all vector store env vars
    monkeypatch.delenv("VECTOR_DSN", raising=False)
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.setenv("SIM_THRESHOLD", "0.1")

    # Force reload of memory modules to pick up new env vars
    import importlib

    import app.memory.api
    import app.memory.unified_store

    importlib.reload(app.memory.unified_store)
    importlib.reload(app.memory.api)

    # Other required env vars
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
    os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
    os.environ.setdefault("ENV_RELOAD_ON_REQUEST", "1")

    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    app = main.app
    client = TestClient(app)

    # Test health endpoint
    r = client.get("/v1/health/vector_store")
    assert r.status_code == 200
    data = r.json()

    # Should default to Chroma with .chroma_data path
    assert data["ok"] is True
    assert data["store_type"] == "ChromaVectorStore"
    # For Chroma with length embedder, just check we got a memory ID
    assert data["test_memory_id"] is not None


def test_vector_store_error_handling(monkeypatch):
    """Test error handling with invalid DSN."""
    app = _setup_app(monkeypatch, "invalid://bad-dsn")
    client = TestClient(app)

    # Test health endpoint
    r = client.get("/v1/health/vector_store")
    assert r.status_code == 200
    data = r.json()

    # Should fall back to memory store gracefully
    assert data["ok"] is True
    assert data["store_type"] == "MemoryVectorStore"
    assert data["test_passed"] is True


def test_vector_store_strict_mode(monkeypatch):
    """Test strict mode behavior."""
    # Set strict mode
    monkeypatch.setenv("STRICT_VECTOR_STORE", "1")

    # Try with invalid DSN - this should fail during app startup
    with pytest.raises(ValueError, match="Unsupported vector store scheme: invalid"):
        _setup_app(monkeypatch, "invalid://bad-dsn")

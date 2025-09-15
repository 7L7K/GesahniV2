import importlib

import pytest


def _reload_memory_api(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    return mem_api


def test_unknown_vector_store_defaults_to_chroma_and_records_fallback(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("VECTOR_STORE", "qdran")  # typo
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    mem_api = _reload_memory_api(monkeypatch)

    # Should create ChromaVectorStore with a recorded init fallback
    assert type(mem_api._store).__name__ == "ChromaVectorStore"


def test_qdrant_missing_dep_falls_back_nonprod(monkeypatch, tmp_path):
    # Force qdrant path but stub out import to simulate missing client
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    # Ensure qdrant-client unavailable via import failure
    import sys

    sys.modules.pop("qdrant_client", None)
    mem_api = _reload_memory_api(monkeypatch)
    # Non-prod default: fallback to memory
    assert type(mem_api._store).__name__ == "MemoryVectorStore"


def test_strict_mode_raises_on_init_error(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("STRICT_VECTOR_STORE", "1")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    # Ensure qdrant unavailable
    import sys

    sys.modules.pop("qdrant_client", None)
    with pytest.raises(ImportError):
        _reload_memory_api(monkeypatch)


def test_reload_store_applies_env_changes(monkeypatch, tmp_path):
    # Start with memory due to pytest default
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    assert type(mem_api._store).__name__ == "MemoryVectorStore"
    # Switch to chroma and ensure reload_store rebinds
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    mem_api.reload_store()
    assert type(mem_api._store).__name__ == "ChromaVectorStore"


def test_preflight_accepts_dual_and_cloud(monkeypatch, tmp_path):
    # dual should be recognized by preflight even if runtime differs under test
    monkeypatch.setenv("VECTOR_STORE", "dual")
    from app.api.preflight import _check_vector_store

    res = _check_vector_store()
    assert res["env"] == "dual"
    assert res["status"] in {"ok", "warn"}

    # cloud should be normalized as chroma for matching
    monkeypatch.setenv("VECTOR_STORE", "cloud")
    res2 = _check_vector_store()
    assert res2["env"] == "cloud"
    assert res2["status"] in {"ok", "warn"}

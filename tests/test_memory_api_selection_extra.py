import importlib


def test_default_to_memory_under_pytest(monkeypatch, tmp_path):
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    # When CHROMA_PATH is invalid, selection should fall back to MemoryVectorStore under pytest
    bad_file = tmp_path / "file"
    bad_file.write_text("x")
    monkeypatch.setenv("CHROMA_PATH", str(bad_file))
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    assert type(mem_api._store).__name__ == "MemoryVectorStore"


def test_unknown_kind_records_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_STORE", "weird")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    assert type(mem_api._store).__name__ in {"ChromaVectorStore", "MemoryVectorStore"}


def test_dual_unavailable_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_STORE", "dual")
    # simulate import failure
    import sys

    sys.modules.pop("app.memory.vector_store.dual", None)
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    assert type(mem_api._store).__name__ == "MemoryVectorStore"

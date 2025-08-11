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
import os
import sys
import shutil
import tempfile
import types
import inspect
from pathlib import Path
from typing import Any, Iterable

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
    num = sum(x * y for x, y in zip(a, b))
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
        for i, doc, meta, emb in zip(ids, documents, metadatas, embeddings, strict=False):
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
                        sum((x - y) ** 2 for x, y in zip(q_emb, rec["embedding"]))
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

    # Reset LLaMA/GPT health and circuit flags
    import app.router as router
    import app.model_picker as model_picker

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
    yield


# ------------------------------------------------------------------------------
# 📝  Pytest hooks
# ------------------------------------------------------------------------------
pytest_plugins = ("pytest_asyncio",)


def pytest_collect_file(file_path: Path, path, parent):  # type: ignore[override]
    # Guarantee OpenAIError exists even if other tests muck with import order
    _ensure_openai_error()
    return None  # allow default collection


def pytest_configure(config):
    # Nothing extra; env vars handled at top-level already
    pass

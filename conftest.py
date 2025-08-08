import math
import os
import sys
import shutil
import tempfile
import types

# Ensure asynchronous tests have an event loop available and JWT auth works.
os.environ.setdefault("JWT_SECRET", "secret")
# Disable debug model routing unless a test explicitly enables it.
os.environ.setdefault("DEBUG_MODEL_ROUTING", "0")

# -----------------------------------------------------------------------
# Always register a ``chromadb`` stub so tests don't depend on the real
# library. If ``chromadb`` is installed, import it and then override the
# modules with the stub.
# -----------------------------------------------------------------------
try:  # pragma: no cover
    import chromadb  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    pass


def _cosine_similarity(a, b):
    denom = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / denom if denom else 0.0


class _CollectionStub:
    def __init__(self, embedding_function=None):
        self._embed = embedding_function or (lambda x: x)
        self._store = {}

    def upsert(self, *, ids, documents, metadatas, embeddings=None):
        embeddings = embeddings or self._embed(documents)
        for i, doc, meta, emb in zip(ids, documents, metadatas, embeddings):
            self._store[i] = {"document": doc, "metadata": meta, "embedding": emb}

    def query(self, *, query_texts, n_results, include=None, where=None):
        q_embs = self._embed(query_texts)
        ids_list, docs_list, metas_list, dists_list = [], [], [], []
        for q_emb in q_embs:
            items = []
            for i, rec in self._store.items():
                if where and any(rec["metadata"].get(k) != v for k, v in where.items()):
                    continue
                dist = 1.0 - _cosine_similarity(q_emb, rec["embedding"])
                items.append((dist, i, rec))
            items.sort(key=lambda x: x[0])
            items = items[:n_results]
            ids_list.append([i for _, i, _ in items])
            docs_list.append([r["document"] for _, _, r in items])
            metas_list.append([r["metadata"] for _, _, r in items])
            dists_list.append([d for d, _, _ in items])
        out = {"ids": ids_list}
        if include is None or "documents" in include:
            out["documents"] = docs_list
        if include is None or "metadatas" in include:
            out["metadatas"] = metas_list
        if include is None or "distances" in include:
            out["distances"] = dists_list
        return out

    def delete(self, *, ids):
        for i in ids:
            self._store.pop(i, None)

    def get(self, include=None):
        return {"ids": list(self._store)}

    def update(self, *, ids, metadatas):
        for i, meta in zip(ids, metadatas):
            if i in self._store:
                self._store[i]["metadata"].update(meta)


class _ClientStub:
    def __init__(self, path=None):
        self._cols = {}

    def get_or_create_collection(self, name, embedding_function=None):
        col = self._cols.get(name)
        if col is None:
            col = _CollectionStub(embedding_function)
            self._cols[name] = col
        return col

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

# Use an isolated temporary directory for any on-disk Chroma data during tests
_prev_chroma = os.environ.get("CHROMA_PATH")
_tmp_chroma = tempfile.mkdtemp(prefix="chroma_test_")
os.environ["CHROMA_PATH"] = _tmp_chroma

def _ensure_openai_error() -> None:
    """Ensure ``openai.OpenAIError`` exists even if tests monkeypatch the module."""
    try:
        sys.modules.pop("openai", None)
        import openai  # type: ignore
        if not hasattr(openai, "OpenAIError"):
            class OpenAIError(Exception): pass
            openai.OpenAIError = OpenAIError  # type: ignore[attr-defined]
    except Exception:
        pass

# Run once at import time
_ensure_openai_error()

def pytest_collect_file(file_path, path, parent):
    _ensure_openai_error()

pytest_plugins = ("pytest_asyncio",)

def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_tmp_chroma, ignore_errors=True)
    if _prev_chroma is not None:
        os.environ["CHROMA_PATH"] = _prev_chroma
    else:
        os.environ.pop("CHROMA_PATH", None)

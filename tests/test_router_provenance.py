import os
import sys
import types
import builtins
import pytest


@pytest.fixture(autouse=True)
def _setup_test_environment(monkeypatch):
    """Set up test environment with proper isolation.

    All module stubs are injected via monkeypatch so they are reverted
    automatically after the test.
    """
    # Basic stubs for modules pulled in by router
    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace())

    fastapi_mod = types.SimpleNamespace()
    fastapi_mod.Depends = lambda *a, **k: None
    fastapi_mod.HTTPException = Exception
    fastapi_mod.status = types.SimpleNamespace()
    fastapi_mod.Request = object
    fastapi_mod.WebSocket = object

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def get(self, *a, **k):
            def decorator(fn):
                return fn
            return decorator

    fastapi_mod.APIRouter = _APIRouter
    fastapi_mod.Query = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "fastapi", fastapi_mod)

    monkeypatch.setitem(
        sys.modules,
        "jwt",
        types.SimpleNamespace(decode=lambda *a, **k: {}, PyJWTError=Exception),
    )
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=object, util=None),
    )
    monkeypatch.setitem(sys.modules, "chromadb", types.SimpleNamespace(PersistentClient=object))
    monkeypatch.setitem(sys.modules, "aiosqlite", types.SimpleNamespace(connect=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "pydantic", types.SimpleNamespace(BaseModel=object))
    monkeypatch.setitem(sys.modules, "aiofiles", types.SimpleNamespace(open=lambda *a, **k: None))
    monkeypatch.setitem(
        sys.modules,
        "rapidfuzz",
        types.SimpleNamespace(fuzz=types.SimpleNamespace(partial_ratio=lambda *a, **k: 0)),
    )
    monkeypatch.setitem(
        sys.modules,
        "tenacity",
        types.SimpleNamespace(
            AsyncRetrying=object,
            stop_after_attempt=lambda *a, **k: None,
            wait_random_exponential=lambda *a, **k: None,
        ),
    )
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace())

    # app.memory shims kept isolated
    env_utils = types.ModuleType("app.memory.env_utils")
    env_utils._get_mem_top_k = lambda: 3
    env_utils._cosine_similarity = lambda a, b: 0.0
    env_utils._normalized_hash = lambda s: s
    monkeypatch.setitem(sys.modules, "app.memory.env_utils", env_utils)

    vector_store = types.ModuleType("app.memory.vector_store")
    vector_store.add_user_memory = lambda *a, **k: None
    vector_store.cache_answer = lambda *a, **k: None
    vector_store.lookup_cached_answer = lambda *a, **k: None
    vector_store.qa_cache = None
    vector_store.get_last_cache_similarity = lambda *a, **k: 0.0
    vector_store.safe_query_user_memories = lambda *a, **k: []
    vector_store._normalized_hash = env_utils._normalized_hash
    monkeypatch.setitem(sys.modules, "app.memory.vector_store", vector_store)

    memory_pkg = types.ModuleType("app.memory")
    memory_pkg.memgpt = types.SimpleNamespace(store_interaction=lambda *a, **k: None)
    memory_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "app.memory", memory_pkg)

    api_module = types.ModuleType("app.memory.api")
    api_module._store = object()
    monkeypatch.setitem(sys.modules, "app.memory.api", api_module)

    memory_store = types.ModuleType("app.memory.memory_store")
    memory_store.MemoryVectorStore = object
    memory_store._get_last_similarity = lambda *a, **k: 0.0
    monkeypatch.setitem(sys.modules, "app.memory.memory_store", memory_store)

    chroma_store = types.ModuleType("app.memory.chroma_store")
    chroma_store.ChromaVectorStore = object
    monkeypatch.setitem(sys.modules, "app.memory.chroma_store", chroma_store)

    class _Emb:
        def create(self, *a, **k):
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0])])

    class _OpenAI:
        def __init__(self, *a, **k):
            self.embeddings = _Emb()

    class _AsyncOpenAI:
        def __init__(self, *a, **k):
            self.embeddings = _Emb()

        async def close(self):
            pass

    class _OpenAIError(Exception):
        pass

    monkeypatch.setattr(builtins, "AsyncOpenAI", _AsyncOpenAI, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(OpenAI=_OpenAI, AsyncOpenAI=_AsyncOpenAI, OpenAIError=_OpenAIError),
    )

    yield


from app import router


def test_annotate_provenance_triggers_embeddings(monkeypatch):
    calls = []

    def fake_embed(text: str):
        calls.append(text)
        return [0.0]

    monkeypatch.setattr(router, "_embed", fake_embed)

    router._annotate_provenance("answer line", ["memory one"])

    assert calls and calls[0] == "memory one"

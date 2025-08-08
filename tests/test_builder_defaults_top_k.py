import sys
import types


class _DummyCollection:
    def add(self, *a, **k):
        pass

    def query(self, *a, **k):
        return {"documents": [[]], "ids": [[]], "metadatas": [[]]}

    def upsert(self, *a, **k):
        pass

    def update(self, *a, **k):
        pass

    def delete(self, *a, **k):
        pass


class _DummyClient:
    def __init__(self, *a, **k):
        pass

    def get_or_create_collection(self, *a, **k):
        return _DummyCollection()


chromadb_stub = types.SimpleNamespace(
    Client=lambda *a, **k: _DummyClient(),
    PersistentClient=lambda *a, **k: _DummyClient(),
)
sys.modules.setdefault("chromadb", chromadb_stub)


class _Settings:
    def __init__(self, *a, **k):
        pass


sys.modules.setdefault("chromadb.config", types.SimpleNamespace(Settings=_Settings))
sys.modules.setdefault(
    "chromadb.utils.embedding_functions",
    types.SimpleNamespace(EmbeddingFunction=object),
)

from app import prompt_builder  # noqa: E402
from app.prompt_builder import PromptBuilder  # noqa: E402


def test_builder_defaults_top_k(monkeypatch):
    monkeypatch.delenv("MEM_TOP_K", raising=False)

    captured: dict[str, int | None] = {}

    def fake_query(uid, q, k=None):
        captured["k"] = k
        return []

    monkeypatch.setattr(
        prompt_builder.memgpt, "summarize_session", lambda sid, user_id=None: ""
    )
    monkeypatch.setattr(prompt_builder, "query_user_memories", fake_query)

    PromptBuilder.build("hi", session_id="s", user_id="u")
    assert captured["k"] == 5

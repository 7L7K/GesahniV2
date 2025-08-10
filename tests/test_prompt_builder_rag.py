import sys
import types

# Stub chromadb for PromptBuilder imports
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


class _DummyRAG:
    def query(self, question, *, collection, k=6):
        return [
            {
                "text": "Detroit saw significant unrest in 1968.",
                "source": "history.txt",
                "loc": "p1",
            }
        ]


def test_prompt_builder_appends_rag_sources(monkeypatch):
    monkeypatch.setattr(prompt_builder.memgpt, "summarize_session", lambda sid, user_id=None: "")
    monkeypatch.setattr(
        prompt_builder, "safe_query_user_memories", lambda uid, q, k=5: []
    )
    prompt, _ = PromptBuilder.build(
        "What happened in Detroit in 1968?",
        session_id="s",
        user_id="u",
        rag_client=_DummyRAG(),
        rag_collection="demo",
    )
    assert "SOURCES" in prompt
    assert "Detroit saw significant unrest in 1968." in prompt
    assert "```history.txt#p1" in prompt

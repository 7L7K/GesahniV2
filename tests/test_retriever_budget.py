import sys
import types

# Minimal chromadb stub
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
    "chromadb.utils.embedding_functions", types.SimpleNamespace(EmbeddingFunction=object)
)

from app.prompt_builder import PromptBuilder
from app import prompt_builder


def test_retriever_budget(monkeypatch):
    monkeypatch.setattr(prompt_builder.memgpt, "summarize_session", lambda sid: "")
    # five memories ~10 tokens each
    mems = [f"memory {i} " * 5 for i in range(5)]
    monkeypatch.setattr(prompt_builder, "query_user_memories", lambda q, k=5: mems[:k])

    base_prompt, base_tokens = PromptBuilder.build("hi", top_k=0)
    prompt, tokens = PromptBuilder.build("hi", top_k=5)

    mem_block = prompt.split("RELEVANT MEMORY", 1)[1].split("USER PROMPT", 1)[0]
    mem_lines = [l for l in mem_block.strip().splitlines() if l.strip()]
    assert len(mem_lines) <= 3
    assert tokens - base_tokens <= 75

import uuid
import time
import os
from typing import List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import EmbeddingFunction

class _LengthEmbeddingFunction(EmbeddingFunction):
    """Simple embedding based on text length to avoid heavy models."""
    def __call__(self, texts: List[str]) -> List[List[float]]:
        return [[float(len(t))] for t in texts]

# Initialize ChromaDB client and collections
_client = chromadb.Client(Settings(anonymized_telemetry=False))
_user_memories = _client.get_or_create_collection(
    "user_memories",
    embedding_function=_LengthEmbeddingFunction(),
)

class _SafeCollection:
    """Wrapper around a ChromaDB collection that tolerates empty deletes."""
    def __init__(self, col):
        self._col = col

    def delete(self, ids=None, **kwargs):
        if not ids:
            return
        return self._col.delete(ids=ids, **kwargs)

    def __getattr__(self, name):
        return getattr(self._col, name)

_qa_cache = _SafeCollection(
    _client.get_or_create_collection(
        "qa_cache", embedding_function=_LengthEmbeddingFunction()
    )
)

def _cache_disabled() -> bool:
    return bool(os.getenv("DISABLE_QA_CACHE"))

def add_user_memory(user_id: str, memory: str) -> str:
    """Store a memory for a user and return the memory id."""
    mem_id = str(uuid.uuid4())
    _user_memories.add(
        ids=[mem_id],
        documents=[memory],
        metadatas=[{"user_id": user_id}],
    )
    return mem_id

def query_user_memories(user_id: str, query: str, n_results: int = 5) -> List[str]:
    """Query memories for a user and return matching documents."""
    results = _user_memories.query(
        query_texts=[query],
        where={"user_id": user_id},
        n_results=n_results
    )
    return results.get("documents", [[]])[0]

def cache_answer(*args: str) -> None:
    """Store an answer in the semantic cache.

    Supports `cache_answer(prompt, answer)` or
    `cache_answer(cache_id, prompt, answer)`.
    """
    if _cache_disabled():
        return
    if len(args) == 2:
        cache_id, prompt, answer = args[0], args[0], args[1]
    elif len(args) == 3:
        cache_id, prompt, answer = args
    else:
        raise TypeError("cache_answer expects 2 or 3 string arguments")

    _qa_cache.upsert(
        ids=[cache_id],
        documents=[prompt],
        metadatas=[{"answer": answer, "timestamp": time.time(), "feedback": None}],
    )

def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
    """Retrieve a cached answer most similar to `prompt`."""
    if _cache_disabled():
        return None

    result = _qa_cache.query(query_texts=[prompt], n_results=1)
    ids = result.get("ids", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    if not ids or not metas:
        return None

    cache_id = ids[0]
    meta = metas[0] or {}
    answer = meta.get("answer")
    fb = meta.get("feedback")
    ts = meta.get("timestamp", 0)

    if fb == "down" or (ts and time.time() - ts > ttl_seconds):
        try:
            _qa_cache.delete(ids=[cache_id])
        finally:
            return None

    return answer

def record_feedback(prompt: str, feedback: str) -> None:
    """Record user feedback ('up' or 'down') for a cached answer."""
    if _cache_disabled():
        return

    result = _qa_cache.query(query_texts=[prompt], n_results=1)
    ids = result.get("ids", [[]])[0]
    if not ids:
        return

    cache_id = ids[0]
    _qa_cache.update(ids=[cache_id], metadatas=[{"feedback": feedback}])

    if feedback == "down":
        try:
            _qa_cache.delete(ids=[cache_id])
        except Exception:
            pass

import uuid
from typing import List, Optional
import time

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
    "user_memories", embedding_function=_LengthEmbeddingFunction()
)
_qa_cache = _client.get_or_create_collection(
    "qa_cache", embedding_function=_LengthEmbeddingFunction()
)


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
        n_results=n_results,
    )
    # returns list of matched documents
    return results.get("documents", [[]])[0]


def cache_answer(prompt_hash: str, answer: str) -> None:
    """Cache an answer using the prompt hash as the id."""
    _qa_cache.upsert(
        ids=[prompt_hash],
        documents=[answer],
        metadatas=[{"timestamp": time.time(), "feedback": None}],
    )


def lookup_cached_answer(prompt_hash: str, ttl_seconds: int = 60 * 60 * 24) -> Optional[str]:
    """Retrieve a cached answer by prompt hash honoring TTL and feedback."""

    result = _qa_cache.get(ids=[prompt_hash])
    docs = result.get("documents")
    metas = result.get("metadatas")
    if not (docs and docs[0]):
        return None

    meta = metas[0] if metas else {}
    fb = meta.get("feedback")
    ts = meta.get("timestamp", 0)
    if fb == "down" or (ts and time.time() - ts > ttl_seconds):
        try:
            _qa_cache.delete(ids=[prompt_hash])
        finally:
            return None
    return docs[0]


def record_feedback(prompt_hash: str, feedback: str) -> None:
    """Record user feedback for a cached answer."""

    _qa_cache.update(ids=[prompt_hash], metadatas=[{"feedback": feedback}])
    if feedback == "down":
        try:
            _qa_cache.delete(ids=[prompt_hash])
        except Exception:
            pass

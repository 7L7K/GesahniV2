import uuid
import time
import os
import hashlib
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
    embedding_function=_LengthEmbeddingFunction()
)
_qa_cache = _client.get_or_create_collection(
    "qa_cache",
    embedding_function=_LengthEmbeddingFunction()
)


def _cache_disabled() -> bool:
    return bool(os.getenv("DISABLE_QA_CACHE") or os.getenv("PYTEST_CURRENT_TEST"))


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


def cache_answer(prompt: str, answer: str) -> None:
    """
    Cache an answer keyed by a hash of the prompt.
    Includes timestamp for TTL and placeholder for user feedback.
    """
    if _cache_disabled():
        return
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    _qa_cache.upsert(
        ids=[prompt_hash],
        documents=[answer],
        metadatas=[{"timestamp": time.time(), "feedback": None}],
    )


def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
    """
    Retrieve a cached answer by prompt, respecting TTL and feedback.
    Returns None if not found, expired, or flagged down.
    """
    if _cache_disabled():
        return None

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    result = _qa_cache.get(ids=[prompt_hash])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    if not docs or not docs[0]:
        return None

    meta = metas[0] or {}
    fb = meta.get("feedback")
    ts = meta.get("timestamp", 0)

    # Delete and return None if negative feedback or expired
    if fb == "down" or (ts and time.time() - ts > ttl_seconds):
        try:
            _qa_cache.delete(ids=[prompt_hash])
        finally:
            return None

    return docs[0]


def record_feedback(prompt: str, feedback: str) -> None:
    """
    Record user feedback ('up' or 'down') for a cached answer.
    Automatically deletes entry if feedback is 'down'.
    """
    if _cache_disabled():
        return

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    _qa_cache.update(
        ids=[prompt_hash],
        metadatas=[{"feedback": feedback}]
    )

    if feedback == "down":
        try:
            _qa_cache.delete(ids=[prompt_hash])
        except Exception:
            pass

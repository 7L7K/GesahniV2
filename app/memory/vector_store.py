import uuid
from typing import List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import EmbeddingFunction
import hashlib
import os


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
        n_results=n_results,
    )
    # returns list of matched documents
    return results.get("documents", [[]])[0]


def cache_answer(prompt: str, answer: str) -> None:
    """Cache an answer keyed by a hash of the prompt."""
    if _cache_disabled():
        return
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    _qa_cache.upsert(
        ids=[prompt_hash],
        documents=[prompt],
        metadatas=[{"answer": answer}],
    )


def lookup_cached_answer(prompt: str) -> Optional[str]:
    """Retrieve a cached answer using the hashed prompt."""
    if _cache_disabled():
        return None
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    result = _qa_cache.get(ids=[prompt_hash])
    metas = result.get("metadatas")
    if metas and metas[0] and "answer" in metas[0]:
        return metas[0]["answer"]
    return None

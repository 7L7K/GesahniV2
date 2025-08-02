import uuid
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


def cache_answer(prompt_hash: str, prompt: str, answer: str) -> None:
    """Cache an answer using the prompt hash as the id.

    The prompt text is stored as the embedded document so that semantic
    similarity search can be performed later. The answer itself is kept in
    the metadata.
    """

    _qa_cache.upsert(
        ids=[prompt_hash],
        documents=[prompt],
        metadatas=[{"answer": answer}],
    )


def lookup_cached_answer(prompt_hash: str) -> Optional[str]:
    """Retrieve a cached answer by prompt hash."""
    result = _qa_cache.get(ids=[prompt_hash])
    metas = result.get("metadatas") or []
    if metas and metas[0]:
        return metas[0].get("answer")
    return None


def lookup_semantic_cached_answer(
    prompt: str, threshold: float = 0.9
) -> Optional[str]:
    """Retrieve a cached answer by semantic similarity.

    ``threshold`` is a simple similarity score derived from the embedding
    distance. With the current length-based embedding, similarity is
    computed as ``1 / (1 + distance)`` which yields ``1.0`` for identical
    lengths.
    """

    result = _qa_cache.query(query_texts=[prompt], n_results=1)
    metas = result.get("metadatas") or []
    distances = result.get("distances") or []
    if not metas or not metas[0] or not distances or not distances[0]:
        return None

    dist = distances[0][0]
    similarity = 1 / (1 + dist)
    if similarity >= threshold:
        return metas[0][0].get("answer") if isinstance(metas[0], list) else metas[0].get("answer")
    return None

from __future__ import annotations

from typing import List, Union

from .models import UserMemory, QACacheEntry

# Simple in-memory stores to simulate a vector database
_user_memories: List[UserMemory] = []
_qa_cache: List[QACacheEntry] = []


def add_user_memory(data: Union[UserMemory, dict]) -> UserMemory:
    """Validate and store a user memory.

    Parameters
    ----------
    data: Union[UserMemory, dict]
        Memory data to validate and insert.
    """

    memory = data if isinstance(data, UserMemory) else UserMemory(**data)
    _user_memories.append(memory)
    return memory


def add_qa_cache_entry(data: Union[QACacheEntry, dict]) -> QACacheEntry:
    """Validate and store a question/answer cache entry."""

    entry = data if isinstance(data, QACacheEntry) else QACacheEntry(**data)
    _qa_cache.append(entry)
    return entry


def get_user_memories() -> List[UserMemory]:
    return list(_user_memories)


def get_qa_cache() -> List[QACacheEntry]:
    return list(_qa_cache)


def clear() -> None:
    _user_memories.clear()
    _qa_cache.clear()

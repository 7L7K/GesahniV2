from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class UserMemory(BaseModel):
    """Representation of a memory from a user session."""

    id: str
    content: str
    embedding: List[float]
    tags: List[str] = Field(default_factory=list)
    timestamp: Optional[str] = None
    session_id: Optional[str] = None


class QACacheEntry(BaseModel):
    """Cached question/answer pair with embedding for retrieval."""

    id: str
    prompt_hash: str
    prompt: str
    answer: str
    embedding: List[float]
    timestamp: Optional[str] = None
    feedback: Optional[str] = None

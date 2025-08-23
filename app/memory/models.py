from __future__ import annotations

from pydantic import BaseModel, Field


class UserMemory(BaseModel):
    """Representation of a memory from a user session."""

    id: str
    content: str
    embedding: list[float]
    tags: list[str] = Field(default_factory=list)
    timestamp: str | None = None
    session_id: str | None = None


class QACacheEntry(BaseModel):
    """Cached question/answer pair with embedding for retrieval."""

    id: str
    prompt_hash: str
    prompt: str
    answer: str
    embedding: list[float]
    timestamp: str | None = None
    feedback: str | None = None

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Any
from contextvars import ContextVar
from hashlib import sha256

from pydantic import BaseModel


def hash_user_id(user_id: str) -> str:
    """Return a stable hash for a user identifier."""
    return sha256(user_id.encode("utf-8")).hexdigest()[:32]


def utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class LogRecord(BaseModel):
    # existing keys
    req_id: str
    prompt: Optional[str] = None
    engine_used: Optional[str] = None
    response: Optional[str] = None
    timestamp: Optional[str] = None

    # core request metadata
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    channel: Optional[str] = None

    # timing & status
    received_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    latency_ms: Optional[int] = None
    p95_latency_ms: Optional[int] = None
    status: Optional[str] = None

    # routing / skills
    matched_skill: Optional[str] = None
    match_confidence: Optional[float] = None
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None

    # llm usage
    model_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cost_usd: Optional[float] = None

    # home assistant audit
    ha_service_called: Optional[str] = None
    entity_ids: Optional[List[str]] = None
    state_before: Optional[Any] = None
    state_after: Optional[Any] = None

    # vector/RAG debugging
    rag_top_k: Optional[int] = None
    rag_doc_ids: Optional[List[str]] = None
    rag_scores: Optional[List[float]] = None
    embed_tokens: Optional[int] = None
    retrieval_count: Optional[int] = None
    cache_hit: Optional[bool] = None


log_record_var: ContextVar[LogRecord | None] = ContextVar("log_record", default=None)

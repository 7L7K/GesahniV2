from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Any, Union
from contextvars import ContextVar
from hashlib import sha256

from pydantic import BaseModel


def hash_user_id(user_id: Optional[Union[str, bytes]]) -> str:
    """Return a stable hash for a user identifier."""
    if user_id is None:
        return "anon"
    if isinstance(user_id, bytes):
        data = user_id
    else:
        data = str(user_id).encode("utf-8")
    return sha256(data).hexdigest()[:32]


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
    prompt_cost_usd: Optional[float] = None
    completion_cost_usd: Optional[float] = None
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

    # deterministic routing / observability
    route_reason: Optional[str] = None
    retrieved_tokens: Optional[int] = None
    self_check_score: Optional[float] = None
    escalated: Optional[bool] = None

    # authentication events
    auth_event_type: Optional[str] = None  # "finish.start", "finish.end", "whoami.start", "whoami.end", "lock.on", "lock.off", "authed.change"
    auth_user_id: Optional[str] = None
    auth_source: Optional[str] = None  # "cookie", "header", "clerk"
    auth_jwt_status: Optional[str] = None  # "ok", "invalid", "missing"
    auth_session_ready: Optional[bool] = None
    auth_is_authenticated: Optional[bool] = None
    auth_lock_reason: Optional[str] = None  # For lock events
    auth_boot_phase: Optional[bool] = None  # True if during boot phase

    # profile facts / KV observability
    profile_facts_keys: Optional[List[str]] = None
    facts_block: Optional[str] = None
    route_trace: Optional[list] = None

    # tts usage
    tts_engine: Optional[str] = None
    tts_tier: Optional[str] = None
    tts_chars: Optional[int] = None
    tts_minutes: Optional[float] = None
    tts_cost_usd: Optional[float] = None


log_record_var: ContextVar[LogRecord | None] = ContextVar("log_record", default=None)

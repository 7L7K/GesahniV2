from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel


def hash_user_id(user_id: str | bytes | None) -> str:
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
    return datetime.now(UTC)


class LogRecord(BaseModel):
    # existing keys
    req_id: str
    prompt: str | None = None
    engine_used: str | None = None
    response: str | None = None
    timestamp: str | None = None

    # core request metadata
    session_id: str | None = None
    user_id: str | None = None
    channel: str | None = None

    # timing & status
    received_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    latency_ms: int | None = None
    p95_latency_ms: int | None = None
    status: str | None = None

    # routing / skills
    matched_skill: str | None = None
    match_confidence: float | None = None
    intent: str | None = None
    intent_confidence: float | None = None

    # llm usage
    model_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_cost_usd: float | None = None
    completion_cost_usd: float | None = None
    cost_usd: float | None = None

    # home assistant audit
    ha_service_called: str | None = None
    entity_ids: list[str] | None = None
    state_before: Any | None = None
    state_after: Any | None = None

    # vector/RAG debugging
    rag_top_k: int | None = None
    rag_doc_ids: list[str] | None = None
    rag_scores: list[float] | None = None
    embed_tokens: int | None = None
    retrieval_count: int | None = None
    cache_hit: bool | None = None

    # deterministic routing / observability
    route_reason: str | None = None
    retrieved_tokens: int | None = None
    self_check_score: float | None = None
    # Optional short human-readable reason set by a matched skill (for logs)
    skill_why: str | None = None
    escalated: bool | None = None
    # standardized skill telemetry
    normalized_prompt: str | None = None
    chosen_skill: str | None = None
    confidence: float | None = None
    slots: dict | None = None
    idempotency_key: str | None = None
    deduped: bool | None = None
    skipped_llm: bool | None = None

    # authentication events
    auth_event_type: str | None = (
        None  # "finish.start", "finish.end", "whoami.start", "whoami.end", "lock.on", "lock.off", "authed.change"
    )
    auth_user_id: str | None = None
    auth_source: str | None = None  # "cookie", "header", "clerk"
    auth_jwt_status: str | None = None  # "ok", "invalid", "missing"
    auth_session_ready: bool | None = None
    auth_is_authenticated: bool | None = None
    auth_lock_reason: str | None = None  # For lock events
    auth_boot_phase: bool | None = None  # True if during boot phase

    # profile facts / KV observability
    profile_facts_keys: list[str] | None = None
    facts_block: str | None = None
    route_trace: list | None = None

    # tts usage
    tts_engine: str | None = None
    tts_tier: str | None = None
    tts_chars: int | None = None
    tts_minutes: float | None = None
    tts_cost_usd: float | None = None


log_record_var: ContextVar[LogRecord | None] = ContextVar("log_record", default=None)

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


_LOCK = threading.RLock()
_MAX = 1000
_BUF: Deque[Dict[str, Any]] = deque(maxlen=_MAX)
_IDX: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_decision(record: Dict[str, Any]) -> None:
    """Insert or update a routing decision entry.

    Expects a dict with at least ``req_id`` and relevant routing fields (engine,
    model_name, route_reason, latency_ms, etc.).
    """

    rid = record.get("req_id")
    if not rid:
        return
    item = {
        "req_id": rid,
        "timestamp": record.get("timestamp") or _now_iso(),
        "engine": record.get("engine_used"),
        "model": record.get("model_name"),
        "route_reason": record.get("route_reason"),
        "latency_ms": record.get("latency_ms"),
        "self_check": record.get("self_check_score"),
        "escalated": record.get("escalated"),
        "cache_hit": record.get("cache_hit"),
        "cache_similarity": record.get("cache_similarity"),
        "retrieved_tokens": record.get("retrieved_tokens"),
        "prompt_tokens": record.get("prompt_tokens"),
        "completion_tokens": record.get("completion_tokens"),
        "rag_doc_ids": record.get("rag_doc_ids"),
        "intent": record.get("intent"),
        "intent_confidence": record.get("intent_confidence"),
        "trace": record.get("route_trace") or [],
    }
    with _LOCK:
        _IDX[rid] = item
        _BUF.append(item)


def get_recent(limit: int = 500) -> List[Dict[str, Any]]:
    with _LOCK:
        return list(_BUF)[-limit:][::-1]


def get_explain(req_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        return _IDX.get(req_id)


def add_trace_event(req_id: str, event: str, **meta: Any) -> None:
    ev = {"t": _now_iso(), "event": event, "meta": meta}
    with _LOCK:
        rec = _IDX.get(req_id)
        if rec is None:
            # seed entry
            rec = {"req_id": req_id, "timestamp": _now_iso(), "trace": []}
            _IDX[req_id] = rec
            _BUF.append(rec)
        trace = rec.setdefault("trace", [])
        trace.append(ev)


__all__ = [
    "add_decision",
    "get_recent",
    "get_explain",
    "add_trace_event",
]



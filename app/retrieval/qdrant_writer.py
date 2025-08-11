from __future__ import annotations

import os
import time
import re
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - optional
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import PointStruct
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore
    PointStruct = object  # type: ignore

from .qdrant_hybrid import _client as _q_client  # reuse URL/key loader
from ..embeddings import embed_sync


def _default_horizon_days(kind: str) -> float:
    if kind.lower() == "event":
        return float(os.getenv("MEMGPT_HORIZON_EVENT_DAYS", "30"))
    if kind.lower() == "preference":
        return float(os.getenv("MEMGPT_HORIZON_PREF_DAYS", "180"))
    # fact/default
    return float(os.getenv("MEMGPT_HORIZON_FACT_DAYS", os.getenv("MEMGPT_HORIZON_DEFAULT_DAYS", "365")))


def _redact_pii(text: str) -> str:
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_re = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}\b")
    ssn_re = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    t = email_re.sub("[PII_EMAIL]", text)
    t = phone_re.sub("[PII_PHONE]", t)
    t = ssn_re.sub("[PII_SSN]", t)
    return t


def upsert_claim(
    *,
    user_id: str,
    doc_id: str,
    text: str,
    claim_type: str,
    entities: List[str] | None = None,
    topic: Optional[str] = None,
    confidence: float = 0.6,
    quality: float = 1.0,
    pinned: bool = False,
    source_tier: float = 0.0,
    decay_at: Optional[float] = None,
    created_at: Optional[float] = None,
    collection: Optional[str] = None,
) -> bool:
    """Upsert a sanitized claim into Qdrant.

    Ensures payload includes the required data model fields and no PII in text.
    """

    if QdrantClient is None:
        return False
    try:
        c = _q_client()
    except Exception:
        return False

    col = collection or os.getenv("QDRANT_COLLECTION") or "kb:default"
    now = time.time()
    created_ts = float(created_at) if created_at is not None else now
    horizon_days = _default_horizon_days(claim_type)
    decay_ts = (
        float(decay_at)
        if decay_at is not None
        else (now + max(1.0, horizon_days * 24.0 * 3600.0))
    )

    red = _redact_pii(text or "")
    vec = embed_sync(red)
    ent = [str(e) for e in (entities or [])][:10]
    top = topic or (ent[0] if ent else claim_type)

    payload: Dict[str, Any] = {
        "doc_id": doc_id,
        "user_id": user_id,
        "type": claim_type,
        "topic": top,
        "entities": ent,
        "created_at": created_ts,
        "checksum": doc_id,
        "source_tier": float(source_tier),
        "quality": float(quality),
        "confidence": float(confidence),
        "pinned": bool(pinned),
        "decay_at": float(decay_ts),
        # text used for semantic search is redacted
        "text": red,
    }

    try:
        c.upsert(collection_name=col, points=[PointStruct(id=doc_id, vector=vec, payload=payload)])
        return True
    except Exception:
        return False


__all__ = ["upsert_claim"]



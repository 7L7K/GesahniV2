# app/health.py
from fastapi import APIRouter
from app.memory.vector_store import add_user_memory
from app.memory.vector_store import query_user_memories as q
from fastapi import Depends, APIRouter
from app.otel_utils import start_span
import os

router = APIRouter()

@router.get("/health/chroma")
def health_chroma():
    user = "diag-health"
    add_user_memory(user, "alpha engines are red")
    add_user_memory(user, "beta engines are blue")
    res = q(user, "tell me about alpha", k=2)
    texts = [getattr(m, "text", getattr(m, "document", "")) for m in res]
    return {"ok": True, "results": texts[:2]}


@router.get("/health/qdrant")
def health_qdrant():
    # Structured span around a simple get_stats call
    try:
        with start_span("qdrant.health"):
            from app.memory.vector_store.qdrant import get_stats as _get_q_stats  # type: ignore

            stats = _get_q_stats()
        return {"ok": True, **stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Note: Router is included by the FastAPI app in main.py; avoid side-effects on import.

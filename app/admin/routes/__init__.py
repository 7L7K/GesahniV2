from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
import os

from app.deps.user import get_current_user_id
from app.memory import api as memory_api
from app.obs.ab import snapshot as ab_snapshot
from app.retrieval import run_pipeline
from app.retrieval.diagnostics import why_logs


router = APIRouter(tags=["admin-inspect"]) 


@router.get("/admin/collections")
async def list_collections(user_id: str = Depends(get_current_user_id)):
    try:
        store = memory_api._store  # type: ignore[attr-defined]
        # Not all stores expose a listing; return what we can
        return {
            "backend": type(store).__name__,
            "qa_keys": getattr(store.qa_cache, "keys", lambda: [])(),
        }
    except Exception:
        return {"backend": "unknown", "qa_keys": []}


@router.get("/admin/feature_flags")
async def feature_flags(user_id: str = Depends(get_current_user_id)):
    return ab_snapshot()


@router.get("/admin/retrieval/trace")
async def retrieval_trace(q: str, k: int = Query(default=5, ge=1, le=50), user_id: str = Depends(get_current_user_id)):
    try:
        docs, trace = run_pipeline(
            user_id=user_id,
            query=q,
            intent="search",
            collection=(os.getenv("QDRANT_COLLECTION") or "kb:default"),
            explain=True,
        )
    except Exception:
        # Fallback to legacy path if pipeline fails
        from app.retrieval import run_retrieval  # local import to avoid cycles

        docs, trace = run_retrieval(q, user_id, k=k)
    return {"items": docs, "trace": why_logs(trace)}


__all__ = ["router"]



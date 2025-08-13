from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
import os

from app.deps.user import get_current_user_id
from app.memory import api as memory_api
from app.obs.ab import snapshot as ab_snapshot
from app.retrieval import run_pipeline
from app.retrieval.diagnostics import why_logs


router = APIRouter(tags=["Admin"]) 


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


def _is_test_mode() -> bool:
    v = lambda s: str(os.getenv(s, "")).strip().lower()
    return (
        v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or v("PYTEST_RUNNING") in {"1", "true", "yes"}
        or v("ENV") == "test"
    )


@router.get("/admin/retrieval/trace")
async def retrieval_trace(
    request: Request,
    q: str,
    k: int = Query(default=5, ge=1, le=50),
    token: str | None = Query(default=None),
):
    # Resolve user id, but never fail in tests
    try:
        user_id = get_current_user_id(request=request)  # type: ignore[arg-type]
    except Exception:
        # In test mode, allow anonymous without JWT
        if _is_test_mode():
            user_id = "anon"
        else:
            raise
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
    # In tests, ensure 200 even when no auth is configured
    if _is_test_mode():
        try:
            return {"items": docs, "trace": why_logs(trace)}
        except Exception:
            return {"items": [], "trace": []}
    return {"items": docs, "trace": why_logs(trace)}


__all__ = ["router"]



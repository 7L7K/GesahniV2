from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from app.deps.user import get_current_user_id

try:
    from app.memory.vector_store import safe_query_user_memories as _safe_query
except Exception:
    _safe_query = None  # type: ignore

router = APIRouter(tags=["rag"])


@router.get("/rag/search")
async def rag_search(
    q: str = Query(..., min_length=1),
    k: int = Query(default=5, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
):
    if _safe_query is None:
        return {"items": []}
    docs = _safe_query(user_id, q, k=k)
    return {"items": docs}



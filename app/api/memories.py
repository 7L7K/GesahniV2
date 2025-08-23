from fastapi import APIRouter, Depends, HTTPException

from app.api._deps import deps_protected_http
from app.deps.user import get_current_user_id

router = APIRouter(tags=["Care"], dependencies=deps_protected_http())


@router.get("/memories/export")
async def export_memories(user_id: str = Depends(get_current_user_id)):
    out = {"profile": [], "episodic": []}
    try:
        from app.memory.api import get_store as _get_vs  # type: ignore

        _vs = _get_vs()
        if hasattr(_vs, "list_user_memories"):
            out["episodic"] = _vs.list_user_memories(user_id)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        from app.memory.memgpt import memgpt

        out["profile"] = memgpt.list_pins()  # type: ignore
    except Exception:
        pass
    return out


@router.delete("/memories/{mem_id}")
async def delete_memory(mem_id: str, user_id: str = Depends(get_current_user_id)):
    try:
        from app.memory.api import get_store as _get_vs  # type: ignore

        _vs = _get_vs()
        if hasattr(_vs, "delete_user_memory"):
            ok = _vs.delete_user_memory(user_id, mem_id)  # type: ignore[attr-defined]
            if ok:
                return {"status": "deleted"}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="memory_not_found")

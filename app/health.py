# app/health.py
from fastapi import APIRouter
from app.memory.vector_store import add_user_memory
from app.memory.vector_store import query_user_memories as q

router = APIRouter()

@router.get("/health/chroma")
def health_chroma():
    user = "diag-health"
    add_user_memory(user, "alpha engines are red")
    add_user_memory(user, "beta engines are blue")
    res = q(user, "tell me about alpha", k=2)
    texts = [getattr(m, "text", getattr(m, "document", "")) for m in res]
    return {"ok": True, "results": texts[:2]}

# Note: Router is included by the FastAPI app in main.py; avoid side-effects on import.

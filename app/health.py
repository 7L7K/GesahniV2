# app/health.py
from fastapi import APIRouter, Depends
from app.memory.vector_store import add_user_memory
from app.memory.vector_store import query_user_memories as q
from fastapi import Depends, APIRouter
from app.otel_utils import start_span
import os

from .deps.scopes import docs_security_with


router = APIRouter(tags=["Admin"], dependencies=[Depends(docs_security_with(["admin:write"]))])

@router.get("/health/vector_store")
def health_vector_store():
    """Comprehensive vector store health check that tells you exactly what's live."""
    try:
        from app.memory.unified_store import get_vector_store_info
        from app.memory.api import get_store
        
        # Get configuration info
        config_info = get_vector_store_info()
        
        # If we're using legacy VECTOR_STORE, the DSN might be converted internally
        # Check if we should show legacy format
        if not os.getenv("VECTOR_DSN") and os.getenv("VECTOR_STORE"):
            legacy_store = os.getenv("VECTOR_STORE", "").strip().lower()
            config_info["dsn"] = f"legacy:{legacy_store}"
        
        # Get actual store instance
        store = get_store()
        store_type = type(store).__name__
        
        # Test basic operations
        test_user = "health-check"
        test_memory = "vector store health check test"
        
        # Add a test memory
        mem_id = add_user_memory(test_user, test_memory)
        
        # Query the memory
        results = q(test_user, "health check", k=1)
        
        # Check if we got our test memory back
        found = False
        if results:
            for result in results:
                if isinstance(result, str):
                    if test_memory in result:
                        found = True
                        break
                elif hasattr(result, 'text') and test_memory in result.text:
                    found = True
                    break
                elif hasattr(result, 'document') and test_memory in result.document:
                    found = True
                    break
        
        # Get backend-specific stats
        backend_stats = {}
        if store_type == "QdrantVectorStore":
            try:
                from app.memory.vector_store.qdrant import get_stats as _get_q_stats
                backend_stats = _get_q_stats()
            except Exception as e:
                backend_stats = {"error": str(e)}
        elif store_type == "ChromaVectorStore":
            backend_stats = {"backend": "chroma", "path": os.getenv("CHROMA_PATH", ".chroma_data")}
        elif store_type == "DualReadVectorStore":
            backend_stats = {"backend": "dual", "primary": "qdrant", "fallback": "chroma"}
        elif store_type == "MemoryVectorStore":
            backend_stats = {"backend": "memory", "note": "ephemeral"}
        
        return {
            "ok": True,
            "store_type": store_type,
            "config": config_info,
            "test_passed": found,
            "test_memory_id": mem_id,
            "backend_stats": backend_stats,
            "embedding_model": os.getenv("EMBED_MODEL", "text-embedding-3-small"),
            "embedding_dim": os.getenv("EMBED_DIM", "1536"),
            "collection": "gesahni_qa",
            "distance_metric": "COSINE"
        }
        
    except Exception as e:
        return {
            "ok": False, 
            "error": str(e),
            "store_type": "unknown",
            "config": {"dsn": os.getenv("VECTOR_DSN", "not set")}
        }


@router.get("/health/chroma")
def health_chroma():
    """Legacy Chroma health check - redirects to unified endpoint."""
    return health_vector_store()


@router.get("/health/qdrant")
def health_qdrant():
    """Legacy Qdrant health check - redirects to unified endpoint."""
    return health_vector_store()

# Note: Router is included by the FastAPI app in main.py; avoid side-effects on import.

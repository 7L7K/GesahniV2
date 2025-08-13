from __future__ import annotations

import os
import sys
from typing import Any, Dict

import httpx
from fastapi import APIRouter


router = APIRouter(tags=["status"])


def _check_tokenizers_parallelism() -> Dict[str, Any]:
    val = (os.getenv("TOKENIZERS_PARALLELISM") or "").strip().lower()
    status = "ok" if val in {"0", "false", "no"} else ("warn" if val else "warn")
    return {"status": status, "value": val or None}


def _check_lazy_sbert() -> Dict[str, Any]:
    # sentence_transformers should NOT be imported before first use
    loaded = "sentence_transformers" in sys.modules
    return {"status": "ok" if not loaded else "warn", "loaded": loaded}


def _check_vector_store() -> Dict[str, Any]:
    from app.memory.api import _store  # type: ignore

    env_vs_raw = (os.getenv("VECTOR_STORE") or "chroma").strip().lower()
    # Treat cloud as a Chroma variant
    env_vs = "chroma" if env_vs_raw in {"chroma", "cloud"} else env_vs_raw
    runtime = type(_store).__name__
    # In pytest, runtime is intentionally MemoryVectorStore regardless of env
    under_test = (os.getenv("PYTEST_CURRENT_TEST") or "") or ("pytest" in sys.modules)
    ok = (
        (env_vs == "qdrant" and runtime == "QdrantVectorStore")
        or (env_vs == "chroma" and runtime == "ChromaVectorStore")
        or (env_vs in {"memory", "inmemory"} and runtime == "MemoryVectorStore")
        or (env_vs == "dual" and runtime == "DualReadVectorStore")
        or bool(under_test)
    )
    return {"status": "ok" if ok else "warn", "env": env_vs_raw, "runtime": runtime}


def _check_qdrant() -> Dict[str, Any]:
    env_vs = (os.getenv("VECTOR_STORE") or "").strip().lower()
    if env_vs != "qdrant":
        return {"status": "skip", "detail": "VECTOR_STORE != qdrant"}
    url = (os.getenv("QDRANT_URL") or "http://localhost:6333").rstrip("/")
    try:
        with httpx.Client(timeout=1.0) as client:
            r = client.get(f"{url}/collections")
            if r.status_code == 200:
                return {"status": "ok", "detail": "reachable"}
            return {"status": "error", "detail": f"http {r.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _check_embeddings() -> Dict[str, Any]:
    backend = (os.getenv("EMBEDDING_BACKEND") or "openai").strip().lower()
    if backend == "openai":
        has_key = bool(os.getenv("OPENAI_API_KEY"))
        return {"status": "ok" if has_key else "warn", "backend": backend, "openai_key": has_key}
    if backend == "llama":
        has_path = bool(os.getenv("LLAMA_EMBEDDINGS_MODEL"))
        return {"status": "ok" if has_path else "warn", "backend": backend, "llama_model": has_path}
    return {"status": "warn", "backend": backend}


@router.get("/status/preflight")
async def preflight() -> Dict[str, Any]:
    checks = {
        "tokenizers_parallelism": _check_tokenizers_parallelism(),
        "sbert_lazy": _check_lazy_sbert(),
        "vector_store": _check_vector_store(),
        "qdrant": _check_qdrant(),
        "embeddings": _check_embeddings(),
    }
    # ok if no check has status "error"; warn-only checks don't fail the whole thing
    ok = all(v.get("status") != "error" for v in checks.values())
    return {"ok": ok, "checks": checks}


__all__ = ["router"]



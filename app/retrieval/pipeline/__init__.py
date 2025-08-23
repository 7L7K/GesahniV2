from __future__ import annotations

import importlib.util

# Compatibility shim: this subpackage name conflicts with the sibling
# module file `app/retrieval/pipeline.py`. Re-export symbols from the
# module file so legacy imports like `from app.retrieval.pipeline import run_retrieval`
# keep working.
import os
from pathlib import Path

_impl_path = Path(__file__).resolve().parent.parent / "pipeline.py"
_spec = importlib.util.spec_from_file_location(
    "app.retrieval._pipeline_impl", str(_impl_path)
)
if _spec and _spec.loader:  # pragma: no cover - import glue
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)  # type: ignore[assignment]
else:  # pragma: no cover - defensive
    raise ImportError("Failed to load retrieval pipeline implementation")

run_pipeline = _mod.run_pipeline


def run_retrieval(q: str, user_id: str, k: int | None = None, **kwargs):
    """Legacy wrapper returning (texts, trace) for admin/diagnostics.

    The new pipeline is intent-aware and collection-based; for tests and
    local diagnostics we pass sensible defaults and ignore `k`.
    """

    coll = os.getenv("QDRANT_COLLECTION") or "kb:default"
    return run_pipeline(
        user_id=user_id, query=q, intent=None, collection=coll, explain=True
    )


__all__ = ["run_pipeline", "run_retrieval"]

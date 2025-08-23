"""Memory utilities for GesahniV2.

This package exposes `MemGPT` from the legacy flat module as well as the new
namespaced `app.memory.memgpt` package to keep imports stable.
"""

try:
    # Prefer the new namespaced package if available
    from .memgpt import MemGPT as MemGPT  # type: ignore
    from .memgpt import memgpt as memgpt  # type: ignore
except Exception:  # pragma: no cover - fallback to legacy flat module
    from . import memgpt as _legacy

    MemGPT = _legacy.MemGPT  # type: ignore
    memgpt = _legacy.memgpt  # type: ignore

__all__ = ["MemGPT", "memgpt"]

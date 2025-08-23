from __future__ import annotations

from typing import List

from ..contracts import MemoryClaim


def should_store(claim: MemoryClaim, *, novelty_tau: float = 0.6, importance_tau: float = 0.6) -> bool:
    """Decide whether to store a claim based on naive thresholds.

    Replace with task-type specific rules as needed.
    """

    return float(claim.confidence) >= min(novelty_tau, importance_tau)


def inject_for_task(task: str, claims: list[MemoryClaim]) -> list[str]:
    """Return lines to inject into prompts for a given task type."""
    if task in {"qa", "chat"}:
        return [c.claim for c in claims if should_store(c)]
    return []


__all__ = ["should_store", "inject_for_task"]



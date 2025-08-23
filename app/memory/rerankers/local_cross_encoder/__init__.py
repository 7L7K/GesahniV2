from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import List

from ..base import Reranker, RerankScore

_logger = logging.getLogger(__name__)  # noqa: F401 (reserved for future debug)


class MiniLMCrossEncoder(Reranker):
    """Lightweight CPU-friendly cross encoder using a length/overlap heuristic.

    This is a deterministic, dependency-free placeholder suitable for dev/tests.
    Replace with sentence-transformers CrossEncoder if GPU/CPU model is desired.
    """

    def rerank(self, query: str, docs: Sequence[str], top_k: int | None = None) -> list[RerankScore]:
        q = set(query.lower().split())
        scores: list[RerankScore] = []
        for idx, d in enumerate(docs):
            toks = set((d or "").lower().split())
            overlap = len(q & toks) / max(1, len(q))
            length_penalty = 1.0 - min(1.0, abs(len(d) - len(query)) / max(len(d), len(query), 1))
            score = 0.7 * overlap + 0.3 * length_penalty
            scores.append(RerankScore(index=idx, score=float(score)))
        scores.sort(key=lambda r: r.score, reverse=True)
        return scores[: top_k or len(scores)]


__all__ = ["MiniLMCrossEncoder"]



from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import List

from ..base import Reranker, RerankScore

_logger = logging.getLogger(__name__)  # noqa: F401 (reserved for future debug)


class CohereReranker(Reranker):
    def rerank(
        self, query: str, docs: Sequence[str], top_k: int | None = None
    ) -> list[RerankScore]:
        # Placeholder adapter – implement with Cohere API if configured
        scores = [RerankScore(index=i, score=float(len(d))) for i, d in enumerate(docs)]
        scores.sort(key=lambda r: r.score, reverse=True)
        return scores[: top_k or len(scores)]


class VoyageReranker(Reranker):
    def rerank(
        self, query: str, docs: Sequence[str], top_k: int | None = None
    ) -> list[RerankScore]:
        scores = [
            RerankScore(index=i, score=float(len(set(query.split()) & set(d.split()))))
            for i, d in enumerate(docs)
        ]
        scores.sort(key=lambda r: r.score, reverse=True)
        return scores[: top_k or len(scores)]


__all__ = ["CohereReranker", "VoyageReranker"]

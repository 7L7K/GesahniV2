from __future__ import annotations

import logging
import os
from typing import List, Sequence

from ..base import RerankScore, Reranker

logger = logging.getLogger(__name__)


class CohereReranker(Reranker):
    def rerank(self, query: str, docs: Sequence[str], top_k: int | None = None) -> List[RerankScore]:
        # Placeholder adapter – implement with Cohere API if configured
        scores = [RerankScore(index=i, score=float(len(d))) for i, d in enumerate(docs)]
        scores.sort(key=lambda r: r.score, reverse=True)
        return scores[: top_k or len(scores)]


class VoyageReranker(Reranker):
    def rerank(self, query: str, docs: Sequence[str], top_k: int | None = None) -> List[RerankScore]:
        scores = [RerankScore(index=i, score=float(len(set(query.split()) & set(d.split())))) for i, d in enumerate(docs)]
        scores.sort(key=lambda r: r.score, reverse=True)
        return scores[: top_k or len(scores)]


__all__ = ["CohereReranker", "VoyageReranker"]



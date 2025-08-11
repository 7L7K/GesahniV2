from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Protocol, Sequence


@dataclass
class RerankScore:
    index: int
    score: float


class Reranker(Protocol):
    def rerank(self, query: str, docs: Sequence[str], top_k: int | None = None) -> List[RerankScore]: ...


__all__ = ["Reranker", "RerankScore"]



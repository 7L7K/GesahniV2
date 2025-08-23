from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import List, Protocol


@dataclass
class RerankScore:
    index: int
    score: float


class Reranker(Protocol):
    def rerank(
        self, query: str, docs: Sequence[str], top_k: int | None = None
    ) -> list[RerankScore]: ...


__all__ = ["Reranker", "RerankScore"]

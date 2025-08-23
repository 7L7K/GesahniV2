from __future__ import annotations

from collections.abc import Iterable

from ..embeddings import embed_sync
from .utils import RetrievedItem


def _cheap_cross_score(query: str, text: str) -> float:
    # Heuristic cross-encoder proxy using cosine between query and doc embeddings,
    # lightly length-normalized to prefer concise passages.
    q = embed_sync(query)
    d = embed_sync(text)
    import math

    dot = sum(x * y for x, y in zip(q, d, strict=False))
    nq = math.sqrt(sum(x * x for x in q)) or 1.0
    nd = math.sqrt(sum(y * y for y in d)) or 1.0
    cos = dot / (nq * nd)
    penalty = 0.02 * max(
        0, (len(text) - 600) / 200
    )  # mild penalty for very long passages
    return float(cos - penalty)


def local_rerank(
    query: str, items: Iterable[RetrievedItem], keep: int
) -> list[RetrievedItem]:
    scored: list[tuple[float, RetrievedItem]] = []
    for it in items:
        s = _cheap_cross_score(query, it.text)
        scored.append((s, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[RetrievedItem] = []
    for s, it in scored[: max(0, keep)]:
        md = dict(it.metadata or {})
        md["local_ce"] = float(s)
        out.append(RetrievedItem(id=it.id, text=it.text, score=float(s), metadata=md))
    return out


def hosted_rerank_passthrough(
    query: str, items: Iterable[RetrievedItem], keep: int
) -> list[RetrievedItem]:
    # Placeholder for a hosted cross-encoder; returns top-N by local score.
    return local_rerank(query, items, keep)


__all__ = ["local_rerank", "hosted_rerank_passthrough"]

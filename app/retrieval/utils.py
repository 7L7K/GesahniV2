from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from ..embeddings import embed_sync


@dataclass
class RetrievedItem:
    """Normalized retrieval item.

    Required fields:
    - id: stable identifier for dedupe and fusion
    - text: document text
    - score: base score from the originating retriever (higher is better)
    - metadata: payload with at least optional fields: created_at, source_tier, pinned, type, topic
    """

    id: str
    text: str
    score: float
    metadata: Dict[str, Any]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RetrievedItem]], *, k: float = 60.0
) -> List[RetrievedItem]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.

    Each input ranking must be in descending relevance order (best first).
    Returns a new list sorted by fused score. The returned items are deep‑copied
    with an attached "rrf_score" in metadata.
    """

    fused: Dict[str, Tuple[RetrievedItem, float]] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            contrib = 1.0 / (k + (rank + 1))
            if item.id in fused:
                base_item, total = fused[item.id]
                fused[item.id] = (base_item, total + contrib)
            else:
                # shallow copy is fine; text/metadata reused
                fused[item.id] = (item, contrib)

    items = []
    for it, s in fused.values():
        md = dict(it.metadata or {})
        md["rrf_score"] = float(s)
        items.append(RetrievedItem(id=it.id, text=it.text, score=float(s), metadata=md))

    items.sort(key=lambda x: x.score, reverse=True)
    return items


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0


def mmr_diversify(
    query: str,
    items: Sequence[RetrievedItem],
    *,
    k: int,
    lambda_: float = 0.6,
) -> List[RetrievedItem]:
    """Select a diverse subset using MMR over embeddings + lexical overlap.

    Diversity is computed as the average of cosine distance in embedding space
    and (1 - Jaccard overlap) over token sets.
    """

    if k <= 0 or not items:
        return []

    q_emb = embed_sync(query)
    item_embs = [embed_sync(it.text) for it in items]
    item_tokens = [_tokenize(it.text) for it in items]

    def _cos_sim(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    selected: List[int] = []
    candidates: List[int] = list(range(len(items)))

    # Seed with the highest base score
    first = max(candidates, key=lambda idx: items[idx].score)
    selected.append(first)
    candidates.remove(first)

    while candidates and len(selected) < k:
        def _mmr_score(idx: int) -> float:
            # relevance: sim(query, doc)
            rel = _cos_sim(q_emb, item_embs[idx])
            # diversity: 1 - max(sim(doc, sel)) with embedding + lexical
            if not selected:
                div = 1.0
            else:
                emb_sims = [_cos_sim(item_embs[idx], item_embs[j]) for j in selected]
                lex_overlaps = [_jaccard(item_tokens[idx], item_tokens[j]) for j in selected]
                # combine similarities then convert to diversity (1 - sim)
                sim = 0.5 * (max(emb_sims) if emb_sims else 0.0) + 0.5 * (
                    max(lex_overlaps) if lex_overlaps else 0.0
                )
                div = 1.0 - sim
            return lambda_ * rel + (1.0 - lambda_) * div

        best = max(candidates, key=_mmr_score)
        selected.append(best)
        candidates.remove(best)

    return [items[i] for i in selected]


def time_decay_boost(
    *,
    timestamp: float | None,
    half_life_days: float,
) -> float:
    """Return a multiplicative time-decay boost in [0, 1]."""

    if not timestamp:
        return 1.0
    import time as _time

    age_sec = max(0.0, float(_time.time() - float(timestamp)))
    half_life_sec = max(1.0, half_life_days * 24.0 * 3600.0)
    # exp(-ln(2) * t / T_half)
    return math.exp(-math.log(2.0) * (age_sec / half_life_sec))


def quality_boost(source_tier: float | None) -> float:
    """Return a multiplicative quality boost based on source tier.

    0.0 → 1.0x, 1.0 → 1.05x, 2.0 → 1.1x, 3.0 → 1.2x ... configurable via env.
    """

    if source_tier is None:
        return 1.0
    base = float(os.getenv("RETRIEVAL_QUALITY_STEP", "0.05"))
    return 1.0 + base * max(0.0, float(source_tier))


def compose_final_score(
    *,
    base: float,
    time_boost: float,
    quality: float,
    pinned: bool,
    weights: Tuple[float, float, float] = (0.7, 0.2, 0.1),
) -> float:
    """Blend base score with boosts and an optional pin bonus.

    final = w0*base + w1*time + w2*quality + pin_bonus
    """

    w0, w1, w2 = weights
    bonus = 0.1 if pinned else 0.0
    return float(w0 * base + w1 * time_boost + w2 * quality + bonus)


def truncate_to_token_budget(texts: List[str], *, max_tokens: int) -> List[str]:
    """Greedy keep from top until token budget is met."""
    from ..token_utils import count_tokens

    out: List[str] = []
    used = 0
    for t in texts:
        c = count_tokens(t)
        if used + c > max_tokens and out:
            break
        out.append(t)
        used += c
    return out


__all__ = [
    "RetrievedItem",
    "reciprocal_rank_fusion",
    "mmr_diversify",
    "time_decay_boost",
    "quality_boost",
    "compose_final_score",
    "truncate_to_token_budget",
]



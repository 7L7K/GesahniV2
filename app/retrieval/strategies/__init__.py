from __future__ import annotations

from typing import List


def hyde_queries(query: str) -> list[str]:
    return [query, f"In other words: {query}"]


def reciprocal_rank_fusion(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for rl in ranked_lists:
        for rank, doc in enumerate(rl, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return [d for d, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


def time_decay(weight_seconds: float) -> float:
    """Monotonic decay in [0,1] that decreases as age increases.

    Uses 1 / (1 + age) so newer (smaller age) yields higher weight.
    """
    try:
        age = float(weight_seconds)
    except Exception:
        age = 0.0
    return max(0.0, min(1.0, 1.0 / (1.0 + age)))


def temporal_boost_order(
    scores: list[float], ages_seconds: list[float], alpha: float = 0.1
) -> list[int]:
    """Return indices sorted by score adjusted with a simple temporal decay.

    Newer items (smaller age) keep more of their base score; older items are penalized.
    adjusted = score - alpha * norm_age, where norm_age in [0,1].
    """
    if not scores:
        return []
    max_age = max(ages_seconds) if ages_seconds else 1.0
    order = list(range(len(scores)))

    def adj(i: int) -> float:
        age = ages_seconds[i] if i < len(ages_seconds) else max_age
        norm_age = (age / max_age) if max_age else 0.0
        return float(scores[i]) - float(alpha) * float(norm_age)

    order.sort(key=lambda i: adj(i), reverse=True)
    return order


__all__ = [
    "hyde_queries",
    "reciprocal_rank_fusion",
    "time_decay",
    "temporal_boost_order",
]

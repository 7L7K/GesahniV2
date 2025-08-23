from __future__ import annotations

import logging
import os
import time
from typing import Any

from ..embeddings import embed_sync
from ..otel_utils import start_span
from ..telemetry import hash_user_id
from ..token_budgeter import _table as _intent_table
from .qdrant_hybrid import dense_search, sparse_search
from .reranker import hosted_rerank_passthrough, local_rerank
from .utils import (
    RetrievedItem,
    compose_final_score,
    mmr_diversify,
    quality_boost,
    reciprocal_rank_fusion,
    time_decay_boost,
    truncate_to_token_budget,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight in-process cache for repeated queries within a short TTL
# ---------------------------------------------------------------------------
_CACHE: dict[tuple[str, str, str | None, str], tuple[list[str], list[dict[str, Any]], float]] = {}

def _normalize_query(q: str) -> str:
    return (q or "").strip().lower()


def _budgets_for_intent(intent: str | None) -> tuple[int, int, int]:
    """Return (k_dense, k_sparse, token_budget) based on task class/intent."""
    max_in, _max_out = _intent_table(intent or "chat")
    # Keep conservative slices per intent; allow overrides via env
    intent_key = (intent or "chat").lower()
    k_dense = int(os.getenv(f"RETRIEVE_{intent_key.upper()}_K_DENSE", "80"))
    k_sparse = int(os.getenv(f"RETRIEVE_{intent_key.upper()}_K_SPARSE", "80"))
    token_budget = int(os.getenv(f"RETRIEVE_{intent_key.upper()}_TOKENS", str(max_in // 2)))
    return k_dense, k_sparse, token_budget


def run_pipeline(
    *,
    user_id: str,
    query: str,
    intent: str | None,
    collection: str,
    explain: bool = False,
    extra_filter: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Execute the end-to-end retrieval pipeline and return (texts, trace).

    Trace contains compact events with reasons and intermediate sizes/scores.
    """

    trace: list[dict[str, Any]] = []
    try:
        user_hash = hash_user_id(str(user_id)) if user_id else "anon"
        logger.info(
            "retrieval.start",
            extra={
                "meta": {
                    "user_hash": user_hash,
                    "intent": (intent or ""),
                    "collection": str(collection),
                    "query_len": len(query or ""),
                }
            },
        )
    except Exception:
        pass
    # Cache check
    cache_ttl = float(os.getenv("RETRIEVE_CACHE_TTL_SECONDS", "0") or 0)
    cache_max = int(os.getenv("RETRIEVE_CACHE_MAX", "128"))
    key = (str(user_id), _normalize_query(query), intent, str(collection))
    now = time.time()
    if cache_ttl > 0:
        cached = _CACHE.get(key)
        if cached and now - cached[2] <= cache_ttl:
            texts, trace_cached, _ts = cached
            trace_cached = list(trace_cached) + [{"event": "cache_hit", "meta": {"age_s": round(now - _ts, 3)}}]
            try:
                logger.info(
                    "retrieval.cache_hit",
                    extra={
                        "meta": {
                            "user_hash": hash_user_id(str(user_id)) if user_id else "anon",
                            "intent": (intent or ""),
                            "collection": str(collection),
                            "age_s": round(now - _ts, 3),
                            "texts": len(texts),
                        }
                    },
                )
            except Exception:
                pass
            return list(texts), trace_cached
    kd, ks, token_budget = _budgets_for_intent(intent)
    trace.append({
        "event": "budget",
        "meta": {
            "intent": (intent or "unknown"),
            "k_dense": kd,
            "k_sparse": ks,
            "token_budget": token_budget,
        },
    })

    # Hybrid search first pass
    t0 = time.perf_counter()
    qvec = embed_sync(query)
    t_embed = (time.perf_counter() - t0) * 1000.0
    dense = []
    sparse = []
    with start_span("vector.qdrant.search", {"k": kd, "filter": str(extra_filter or {})}):
        t1 = time.perf_counter()
        try:
            dense = dense_search(collection=collection, user_id=user_id, query_vector=qvec, limit=kd, extra_filter=extra_filter)
        except Exception:
            dense = []
        t_vec = (time.perf_counter() - t1) * 1000.0
    with start_span("vector.qdrant.search", {"k": ks, "filter": str(extra_filter or {}), "sparse": True}):
        t2 = time.perf_counter()
        try:
            sparse = sparse_search(collection=collection, user_id=user_id, query=query, limit=ks, extra_filter=extra_filter)
        except Exception:
            sparse = []
        t_sparse = (time.perf_counter() - t2) * 1000.0
    # Threshold filtering policy (best-effort)
    dense_thresh = float(os.getenv("RETRIEVE_DENSE_SIM_THRESHOLD", "0.75"))
    if dense:
        try:
            dense = [it for it in dense if float(getattr(it, "score", 0.0) or 0.0) >= dense_thresh]
        except Exception:
            pass
    # Include threshold rationale snapshot: first few raw scores and keep/drop
    def _sample_scores(items):
        return [round(float(getattr(it, 'score', 0.0) or 0.0), 4) for it in items[:5]]
    trace.append({
        "event": "hybrid",
        "meta": {
            "dense": len(dense),
            "sparse": len(sparse),
            "t_embed_ms": int(t_embed),
            "t_vec_ms": int(t_vec),
            "t_sparse_ms": int(t_sparse),
            "scores_dense": _sample_scores(dense),
            "scores_sparse": _sample_scores(sparse),
            "threshold_sim": round(dense_thresh, 4),
            "policy": f"keep if sim>={dense_thresh} (dist<={round(1.0-dense_thresh,4)})",
        },
    })

    # RRF (include simple feature breakdown sample)
    t3 = time.perf_counter()
    with start_span("retrieval.pipeline", {"topk_pre": len(dense) + len(sparse)}):
        fused = reciprocal_rank_fusion([dense, sparse]) if (dense or sparse) else []
    t_rrf = (time.perf_counter() - t3) * 1000.0
    def _rrf_features(fused_items: list[RetrievedItem]) -> list[dict[str, float]]:
        rows: list[dict[str, float]] = []
        for it in fused_items[:5]:
            md = it.metadata or {}
            rows.append({
                "rrf_score": float(md.get("rrf_score", it.score)),
                "base": float(md.get("base", 0.0)),
            })
        return rows
    trace.append({
        "event": "rrf",
        "meta": {
            "in_dense": len(dense),
            "in_sparse": len(sparse),
            "out": len(fused),
            "t_ms": int(t_rrf),
            "features": _rrf_features(fused),
        },
    })

    # Diversify via MMR (cap pool to 200 for speed, select 60 by default)
    max_pool = int(os.getenv("RETRIEVE_POOL_MAX", "200"))
    mmr_k = int(os.getenv("RETRIEVE_MMR_K", "60"))
    pool = fused[:max_pool]
    t4 = time.perf_counter()
    mmr_lambda = float(os.getenv("RETRIEVE_MMR_LAMBDA", "0.6"))
    with start_span("retrieval.pipeline", {"mmr": True, "topk_pre": len(pool)}):
        diversified = mmr_diversify(query, pool, k=min(mmr_k, len(pool)), lambda_=mmr_lambda)
    t_mmr = (time.perf_counter() - t4) * 1000.0
    # diversity proxy: average pairwise Jaccard distance over tokens for selection
    def _diversity_score(items: list[str]) -> float:
        toks = [set(x.lower().split()) for x in items]
        if len(toks) < 2:
            return 0.0
        pairs = 0
        acc = 0.0
        for i in range(len(toks)):
            for j in range(i + 1, len(toks)):
                inter = len(toks[i] & toks[j])
                union = max(1, len(toks[i] | toks[j]))
                acc += 1.0 - (inter / union)
                pairs += 1
        return float(acc / max(1, pairs))
    before_div = _diversity_score([it.text for it in pool[:10]])
    after_div = _diversity_score([it.text for it in diversified[:10]])
    trace.append({
        "event": "mmr",
        "meta": {
            "in": len(pool),
            "out": len(diversified),
            "lambda": round(mmr_lambda, 3),
            "t_ms": int(t_mmr),
            "diversity_before": round(before_div, 3),
            "diversity_after": round(after_div, 3),
            "diversity_delta": round(after_div - before_div, 3),
            "sample_ids": [it.id for it in diversified[:5]],
        },
    })

    # Rerank cascade: local then optional hosted
    keep1 = int(os.getenv("RETRIEVE_CE_KEEP1", "24"))
    keep2 = int(os.getenv("RETRIEVE_CE_KEEP2", "12"))
    t5 = time.perf_counter()
    after_local = local_rerank(query, diversified, keep=keep1)
    t_rerank1 = (time.perf_counter() - t5) * 1000.0
    ce_scores = [float(it.metadata.get("local_ce", 0.0)) for it in after_local]
    ce_top = ce_scores[0] if ce_scores else 0.0
    ce_avg = (sum(ce_scores) / len(ce_scores)) if ce_scores else 0.0
    trace.append({
        "event": "rerank_local",
        "meta": {
            "in": len(diversified),
            "out": len(after_local),
            "t_ms": int(t_rerank1),
            "ce_top": round(ce_top, 3),
            "ce_avg": round(ce_avg, 3),
            "kept_ids": [it.id for it in after_local[:10]],
        },
    })
    use_hosted = os.getenv("RETRIEVE_USE_HOSTED_CE", "0").lower() in {"1", "true", "yes"}
    t6 = time.perf_counter()
    after_hosted = hosted_rerank_passthrough(query, after_local, keep=keep2) if use_hosted else after_local[:keep2]
    t_rerank2 = (time.perf_counter() - t6) * 1000.0
    ce2_scores = [float(it.metadata.get("local_ce", 0.0)) for it in after_hosted]
    ce2_avg = (sum(ce2_scores) / len(ce2_scores)) if ce2_scores else 0.0
    trace.append({
        "event": "rerank_hosted",
        "meta": {
            "enabled": use_hosted,
            "in": len(after_local),
            "out": len(after_hosted),
            "t_ms": int(t_rerank2),
            "hosted_calls": int(use_hosted),
            "score_avg": round(ce2_avg, 3),
            "kept_ids": [it.id for it in after_hosted[:10]],
        },
    })

    # Temporal & quality boost, compose final scores
    half_life_days = float(os.getenv("RETRIEVE_HALF_LIFE_DAYS", "14"))
    finalized: list[tuple[float, RetrievedItem, dict[str, Any]]] = []
    for it in after_hosted:
        ts = None
        tier = None
        pinned = False
        try:
            ts = float(it.metadata.get("created_at", 0) or 0)
        except Exception:
            ts = None
        try:
            tier = float(it.metadata.get("source_tier", 0) or 0)
        except Exception:
            tier = None
        pinned = bool(it.metadata.get("pinned", False))
        tb = time_decay_boost(timestamp=ts, half_life_days=half_life_days)
        qb = quality_boost(tier)
        final = compose_final_score(base=it.score, time_boost=tb, quality=qb, pinned=pinned)
        meta = {
            "base": it.score,
            "time_boost": tb,
            "quality_boost": qb,
            "pinned": pinned,
            "final": final,
        }
        finalized.append((final, it, meta))

    finalized.sort(key=lambda x: x[0], reverse=True)
    top_items = [it for _f, it, _m in finalized]
    top_meta = [m for _f, _it, m in finalized]
    # Include boost configuration and sample math for first few items
    weights = (0.7, 0.2, 0.1)
    examples = []
    for i in range(min(3, len(top_items))):
        ex = top_meta[i]
        examples.append({
            "base": round(float(ex["base"]), 4),
            "time": round(float(ex["time_boost"]), 4),
            "quality": round(float(ex["quality_boost"]), 4),
            "pinned": bool(ex["pinned"]),
            "final": round(float(ex["final"]), 4),
            "formula": "final = 0.7*base + 0.2*time + 0.1*quality + (pinned?0.1:0)",
        })
    trace.append({
        "event": "boost",
        "meta": {
            "count": len(top_items),
            "half_life_days": half_life_days,
            "weights": weights,
            "examples": examples,
        },
    })

    # MemGPT/task policy trim: enforce token budget and minimal decision trail
    # Include mem_documents as-is; downstream caps to 500–600 tokens via truncate_to_token_budget
    texts = [it.text for it in top_items]
    trimmed = truncate_to_token_budget(texts, max_tokens=token_budget)
    if not trimmed and texts:
        trimmed = texts[:1]
    # Ensure at least one trace note about decision trail items count
    trace.append({"event": "policy_trim", "meta": {"kept": len(trimmed), "budget_tokens": token_budget}})

    # Explainability: include top reasons and composite scores for the first N,
    # respecting a per-task injection policy (e.g., HA constraints)
    allowed_types_by_intent = {
        "ha": {"device", "location", "safety", "rollup:device", "rollup:location", "rollup:safety"},
    }
    allow_set = allowed_types_by_intent.get((intent or "").lower())
    filtered_items = []
    if allow_set:
        for it in top_items:
            t = str(it.metadata.get("type") or "").lower()
            if t in allow_set:
                filtered_items.append(it)
        if filtered_items:
            top_items = filtered_items
            top_meta = [m for _f, _it, m in finalized if _it in top_items]
    expl_count = min(5, len(top_items))
    explain_rows: list[dict[str, Any]] = []
    for i in range(expl_count):
        it = top_items[i]
        em = top_meta[i]
        explain_rows.append(
            {
                "id": it.id,
                "final": round(float(em["final"]), 4),
                "reasons": {
                    "entity_match": True,  # implicit via retrieval
                    "recency": round(float(em["time_boost"]), 3),
                    "quality": round(float(em["quality_boost"]), 3),
                    "pinned": bool(em["pinned"]),
                    "diversity_gain": True,
                },
            }
        )
    if explain:
        trace.append({"event": "explain", "meta": {"items": explain_rows}})

    # Cache store
    if cache_ttl > 0:
        try:
            if len(_CACHE) >= cache_max:
                # drop oldest entry (simple heuristic: pop arbitrary)
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = (list(trimmed), list(trace), now)
        except Exception:
            pass
    try:
        logger.info(
            "retrieval.finish",
            extra={
                "meta": {
                    "user_hash": hash_user_id(str(user_id)) if user_id else "anon",
                    "intent": (intent or ""),
                    "collection": str(collection),
                    "input_len": len(query or ""),
                    "kept": len(trimmed),
                    "trace_len": len(trace),
                    "k_dense": kd,
                    "k_sparse": ks,
                }
            },
        )
    except Exception:
        pass
    return trimmed, trace


__all__ = ["run_pipeline"]



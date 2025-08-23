from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


def _as_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(val: str | None, default: float) -> float:
    try:
        return float(val) if val is not None else float(default)
    except Exception:
        return float(default)


def _as_int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None else int(default)
    except Exception:
        return int(default)


def _as_set_csv(val: str | None) -> set[str]:
    if not val:
        return set()
    return {p.strip().lower() for p in val.split(",") if p.strip()}


@dataclass(frozen=True)
class StoreCfg:
    vector_store: str
    qdrant_url: str
    qdrant_collection: str
    embed_dim: int
    use_quantization: bool


@dataclass(frozen=True)
class RetrievalCfg:
    topk_vec: int
    topk_final: int
    use_hyde: bool
    use_mmr: bool
    mmr_lambda: float
    use_hybrid: bool
    hybrid_weight_dense: float


@dataclass(frozen=True)
class RerankCfg:
    cascade: bool
    local_model: str
    hosted: str
    gate_low: float


@dataclass(frozen=True)
class MemGPTCfg:
    policy: str
    write_quota_per_session: int
    importance_tau: float
    novelty_tau: float


@dataclass(frozen=True)
class ObsCfg:
    trace_sample_rate: float
    latency_budget_ms: int
    ablation_flags: set[str]


@dataclass(frozen=True)
class RuntimeConfig:
    store: StoreCfg
    retrieval: RetrievalCfg
    rerank: RerankCfg
    memgpt: MemGPTCfg
    obs: ObsCfg

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["obs"]["ablation_flags"] = sorted(self.obs.ablation_flags)
        return d


def _load_config() -> RuntimeConfig:
    store = StoreCfg(
        vector_store=os.getenv("VECTOR_STORE", "chroma").strip().lower(),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "kb:default"),
        embed_dim=_as_int(os.getenv("EMBED_DIM"), 1536),
        use_quantization=_as_bool(os.getenv("USE_QUANTIZATION"), False),
    )
    retrieval = RetrievalCfg(
        topk_vec=_as_int(os.getenv("TOPK_VEC"), 120),
        topk_final=_as_int(os.getenv("TOPK_FINAL"), 12),
        use_hyde=_as_bool(os.getenv("USE_HYDE"), False),
        use_mmr=_as_bool(os.getenv("USE_MMR"), True),
        mmr_lambda=_as_float(os.getenv("MMR_LAMBDA"), 0.3),
        use_hybrid=_as_bool(os.getenv("USE_HYBRID"), False),
        hybrid_weight_dense=_as_float(os.getenv("HYBRID_WEIGHT_DENSE"), 0.6),
    )
    rerank = RerankCfg(
        cascade=_as_bool(os.getenv("RERANK_CASCADE"), True),
        local_model=os.getenv("RERANK_LOCAL_MODEL", "minilm").strip().lower(),
        hosted=os.getenv("RERANK_HOSTED", "").strip().lower(),
        gate_low=_as_float(os.getenv("RERANK_GATE_LOW"), 0.0),
    )
    memgpt = MemGPTCfg(
        policy=os.getenv("MEM_POLICY", "default"),
        write_quota_per_session=_as_int(os.getenv("MEM_WRITE_QUOTA_PER_SESSION"), 30),
        importance_tau=_as_float(os.getenv("MEM_IMPORTANCE_TAU"), 0.7),
        novelty_tau=_as_float(os.getenv("MEM_NOVELTY_TAU"), 0.55),
    )
    obs = ObsCfg(
        trace_sample_rate=_as_float(os.getenv("TRACE_SAMPLE_RATE"), 0.2),
        latency_budget_ms=_as_int(os.getenv("LATENCY_BUDGET_MS"), 900),
        ablation_flags=_as_set_csv(os.getenv("ABLATION_FLAGS")),
    )
    return RuntimeConfig(store, retrieval, rerank, memgpt, obs)


# Read once at import (startup)
_CONFIG: RuntimeConfig = _load_config()


def get_config() -> RuntimeConfig:
    # In tests, reflect the latest environment on each call so monkeypatched
    # env vars take effect immediately without having to restart the app.
    if os.getenv("PYTEST_RUNNING", "").strip().lower() in {"1", "true", "yes"}:
        return _load_config()
    return _CONFIG


__all__ = ["RuntimeConfig", "get_config"]

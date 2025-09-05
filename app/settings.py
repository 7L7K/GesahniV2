from __future__ import annotations

import os
from typing import List


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def router_default_model() -> str:
    return os.getenv("ROUTER_DEFAULT_MODEL", "gpt-4o-mini")


def router_budget_ms() -> int:
    return int(os.getenv("ROUTER_BUDGET_MS", "120000") or 120000)


def backend_timeout_ms() -> int:
    return int(os.getenv("BACKEND_TIMEOUT_MS", "30000") or 30000)


def circuit_breaker_cooldown_s() -> int:
    return int(os.getenv("CIRCUIT_BREAKER_COOLDOWN_S", "20") or 20)


def cache_ttl_s() -> int:
    return int(os.getenv("CACHE_TTL_S", "600") or 600)


def cache_max_entries() -> int:
    return int(os.getenv("CACHE_MAX_ENTRIES", "10000") or 10000)


def allowlist_models() -> List[str]:
    raw = os.getenv("ALLOWLIST_MODELS", "")
    return [m for m in (s.strip() for s in raw.split(",")) if m]


def dry_run() -> bool:
    return _truthy(os.getenv("DRY_RUN", "0"))


def auth_dev_bypass() -> bool:
    return _truthy(os.getenv("AUTH_DEV_BYPASS", "0"))


def skills_version() -> str:
    return os.getenv("SKILLS_VERSION", "0")


def stream_stall_ms() -> int:
    return int(os.getenv("STREAM_STALL_MS", "15000") or 15000)


# Optional compatibility getter (not required but useful in fallback flows)
def prompt_backend() -> str:
    return os.getenv("PROMPT_BACKEND", "live").strip().lower()


def debug_model_routing() -> bool:
    return _truthy(os.getenv("DEBUG_MODEL_ROUTING", "0"))


def router_rules_path() -> str:
    return os.getenv("ROUTER_RULES_PATH", "router_rules.yaml")


def openai_timeout_ms() -> int:
    return int(os.getenv("OPENAI_TIMEOUT_MS", "6000") or 6000)


def ollama_timeout_ms() -> int:
    return int(os.getenv("OLLAMA_TIMEOUT_MS", "4500") or 4500)


def allowed_gpt_models() -> list[str]:
    raw = os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo")
    return [m for m in raw.split(",") if m]


def allowed_llama_models() -> list[str]:
    raw = os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3")
    return [m for m in raw.split(",") if m]


def llama_user_cb_threshold() -> int:
    return int(os.getenv("LLAMA_USER_CB_THRESHOLD", "3") or 3)


def llama_user_cb_cooldown() -> float:
    return float(os.getenv("LLAMA_USER_CB_COOLDOWN", "120") or 120)


def model_router_heavy_words() -> int:
    return int(os.getenv("MODEL_ROUTER_HEAVY_WORDS", "30") or 30)


def model_router_heavy_tokens() -> int:
    return int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "1000") or 1000)


def sim_threshold() -> float:
    return float(os.getenv("SIM_THRESHOLD", "0.24") or 0.24)


# Admin/integrations helpers -------------------------------------------------
def qdrant_collection() -> str:
    return os.getenv("QDRANT_COLLECTION", "kb:default")


def strict_vector_store() -> bool:
    return _truthy(os.getenv("STRICT_VECTOR_STORE", "0"))


def embed_dim() -> int:
    return int(os.getenv("EMBED_DIM", "1536") or 1536)


def google_client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "")


def google_redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", "")

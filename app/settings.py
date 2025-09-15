import os
from collections.abc import Iterable

try:
    # pydantic v2 moved BaseSettings to pydantic-settings package
    from pydantic_settings import BaseSettings  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    BaseSettings = None


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


# ----------------------------------------------------------------------------
# Object settings (lightweight; only a few core fields)
# ----------------------------------------------------------------------------
if BaseSettings:

    class Settings(BaseSettings):
        # When True, enforce strict token/contracts and issuer checks. Default True for prod.
        STRICT_CONTRACTS: bool = True

        # Allow tests to skip optional external probes when False
        OPTIONAL_PROBES_ENABLED: bool = True

        # Default HTTP client timeout in seconds
        HTTP_CLIENT_TIMEOUT: float = 10.0

        # Test-mode flag (tests may toggle explicitly)
        TEST_MODE: bool = False

        class Config:
            env_prefix = "GESAHNI_"
            case_sensitive = False

    # Module-level singleton for easy import
    settings = Settings()
else:
    # Minimal fallback Settings implementation that reads from environment.
    class Settings:
        def __init__(self) -> None:
            prefix = "GESAHNI_"
            self.STRICT_CONTRACTS = _truthy(os.getenv(prefix + "STRICT_CONTRACTS", "1"))
            self.OPTIONAL_PROBES_ENABLED = _truthy(
                os.getenv(prefix + "OPTIONAL_PROBES_ENABLED", "1")
            )
            self.HTTP_CLIENT_TIMEOUT = float(
                os.getenv(prefix + "HTTP_CLIENT_TIMEOUT", "10.0")
            )
            self.TEST_MODE = _truthy(os.getenv(prefix + "TEST_MODE", "0"))

    settings = Settings()


# ----------------------------------------------------------------------------
# Functional settings API used by router leaf modules
# ----------------------------------------------------------------------------


def _split_csv(env_value: str | None, default: Iterable[str]) -> list[str]:
    raw = (env_value or "").strip()
    if not raw:
        return list(default)
    return [p.strip() for p in raw.split(",") if p.strip()]


def allowed_gpt_models() -> list[str]:
    return _split_csv(
        os.getenv("ALLOWED_GPT_MODELS"), ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]
    )


def allowed_llama_models() -> list[str]:
    return _split_csv(
        os.getenv("ALLOWED_LLAMA_MODELS"), ["llama3", "llama3:latest", "llama3.1"]
    )


def openai_timeout_ms() -> int:
    try:
        return int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
    except Exception:
        return 6000


def ollama_timeout_ms() -> int:
    try:
        return int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))
    except Exception:
        return 4500


def router_budget_ms() -> int:
    try:
        return int(os.getenv("ROUTER_BUDGET_MS", "7000"))
    except Exception:
        return 7000


def llama_user_cb_threshold() -> int:
    try:
        return int(os.getenv("LLAMA_USER_CB_THRESHOLD", "3"))
    except Exception:
        return 3


def llama_user_cb_cooldown() -> int:
    try:
        return int(os.getenv("LLAMA_USER_CB_COOLDOWN", "120"))
    except Exception:
        return 120


def model_router_heavy_words() -> int:
    try:
        return int(os.getenv("MODEL_ROUTER_HEAVY_WORDS", "30"))
    except Exception:
        return 30


def model_router_heavy_tokens() -> int:
    try:
        return int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "1000"))
    except Exception:
        return 1000


def sim_threshold() -> float:
    from .memory.env_utils import DEFAULT_SIM_THRESHOLD

    raw = os.getenv("SIM_THRESHOLD")
    try:
        v = float(raw) if raw is not None else DEFAULT_SIM_THRESHOLD
    except Exception:
        return DEFAULT_SIM_THRESHOLD
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def router_rules_path() -> str:
    return os.getenv("ROUTER_RULES_PATH", "router_rules.yaml")


def router_default_model() -> str:
    return os.getenv("ROUTER_DEFAULT_MODEL", "gpt-4o")


def backend_timeout_ms() -> int:
    try:
        return int(os.getenv("BACKEND_TIMEOUT_MS", "6000"))
    except Exception:
        return 6000


def circuit_breaker_cooldown_s() -> int:
    try:
        return int(os.getenv("CB_COOLDOWN_S", "60"))
    except Exception:
        return 60


def cache_ttl_s() -> int:
    try:
        return int(os.getenv("CACHE_TTL_S", "60"))
    except Exception:
        return 60


def cache_max_entries() -> int:
    try:
        return int(os.getenv("CACHE_MAX_ENTRIES", "200"))
    except Exception:
        return 200


def allowlist_models() -> list[str]:
    return allowed_gpt_models() + allowed_llama_models()


def dry_run() -> bool:
    # Dry-run is tied to debug flag in this codebase; keep minimal here
    return debug_model_routing()


def auth_dev_bypass() -> bool:
    return os.getenv("AUTH_DEV_BYPASS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def skills_version() -> str:
    return os.getenv("SKILLS_VERSION", "v1")


def stream_stall_ms() -> int:
    try:
        return int(os.getenv("STREAM_STALL_MS", "1000"))
    except Exception:
        return 1000


def prompt_backend() -> str:
    return os.getenv("PROMPT_BACKEND", "live").lower()


def google_client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "test-client-id")


def google_redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/v1/google/callback")


def qdrant_collection() -> str:
    return os.getenv("QDRANT_COLLECTION", "gesahni")


def strict_vector_store() -> bool:
    return os.getenv("STRICT_VECTOR_STORE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def embed_dim() -> int:
    try:
        return int(os.getenv("EMBED_DIM", "384"))
    except Exception:
        return 384


def debug_model_routing() -> bool:
    return os.getenv("DEBUG_MODEL_ROUTING", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

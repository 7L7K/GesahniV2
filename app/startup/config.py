from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class StartupProfile:
    name: str
    components: tuple[str, ...]  # names in components.py to run in order

def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}

def detect_profile() -> StartupProfile:
    env = (os.getenv("ENV") or "dev").strip().lower()
    dev_mode = _is_truthy(os.getenv("DEV_MODE"))
    in_ci = _is_truthy(os.getenv("CI")) or "PYTEST_CURRENT_TEST" in os.environ
    chaos_mode = _is_truthy(os.getenv("CHAOS_MODE"))

    # Base components (keep order deterministic)
    base = (
        "init_database",
        "init_database_migrations",
        "init_token_store_schema",
        "init_openai_health_check",
        "init_vector_store",
        "init_memory_store",
        "init_scheduler",
        "init_client_warmup",
    )
    ha = ("init_home_assistant",)
    llama = ("init_llama",)

    if in_ci:
        # CI/Test: zero heavy externals; keep memory/local only
        return StartupProfile("ci", ("init_database", "init_database_migrations", "init_token_store_schema", "init_memory_store"))

    if env in {"prod", "production"} and not dev_mode:
        # Full fat: everything on
        return StartupProfile("prod", base + llama + ha)

    # Dev: no HA/LLAMA by default, unless explicitly enabled
    want_llama = _is_truthy(os.getenv("LLAMA_ENABLED"))
    want_ha = _is_truthy(os.getenv("HOME_ASSISTANT_ENABLED"))
    extra = (() if not want_llama else llama) + (() if not want_ha else ha) + ("init_dev_user",)

    # Add chaos mode component if enabled
    if chaos_mode and env == "dev":
        extra = extra + ("init_chaos_mode",)

    return StartupProfile("dev", base + extra)



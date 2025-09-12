"""Router policy constants and configuration.

This module contains all router-related constants and policy settings.
Leaf modules should import from here instead of defining their own constants.
"""

from app import settings


# Model allow-lists (single source of truth)
def _get_allowed_models() -> tuple[set[str], set[str]]:
    """Get allowed models from centralized settings."""
    gpt_models = set(settings.allowed_gpt_models())
    llama_models = set(settings.allowed_llama_models())
    return gpt_models, llama_models


ALLOWED_GPT_MODELS, ALLOWED_LLAMA_MODELS = _get_allowed_models()


# Timeout configurations
OPENAI_TIMEOUT_MS = settings.openai_timeout_ms()
OLLAMA_TIMEOUT_MS = settings.ollama_timeout_ms()


# Budget configurations
ROUTER_BUDGET_MS = settings.router_budget_ms()


# Circuit breaker thresholds
LLAMA_USER_CB_THRESHOLD = settings.llama_user_cb_threshold()
LLAMA_USER_CB_COOLDOWN = settings.llama_user_cb_cooldown()


# Model routing configurations
MODEL_ROUTER_HEAVY_WORDS = settings.model_router_heavy_words()
MODEL_ROUTER_HEAVY_TOKENS = settings.model_router_heavy_tokens()


# Intent detection threshold
SIM_THRESHOLD = settings.sim_threshold()

# Prompt backend configuration - for safe development and testing
PROMPT_BACKEND = settings.prompt_backend()

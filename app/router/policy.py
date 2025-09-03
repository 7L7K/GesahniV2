"""Router policy constants and configuration.

This module contains all router-related constants and policy settings.
Leaf modules should import from here instead of defining their own constants.
"""
import os
from typing import Set


# Model allow-lists (single source of truth)
def _get_allowed_models() -> tuple[Set[str], Set[str]]:
    """Get allowed models from environment variables as sets."""
    gpt_models = set(
        filter(
            None,
            os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(","),
        )
    )
    llama_models = set(
        filter(
            None, os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(",")
        )
    )
    return gpt_models, llama_models


ALLOWED_GPT_MODELS, ALLOWED_LLAMA_MODELS = _get_allowed_models()


# Timeout configurations
OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))


# Budget configurations
ROUTER_BUDGET_MS = int(os.getenv("ROUTER_BUDGET_MS", "7000"))


# Circuit breaker thresholds
LLAMA_USER_CB_THRESHOLD = int(os.getenv("LLAMA_USER_CB_THRESHOLD", "3"))
LLAMA_USER_CB_COOLDOWN = float(os.getenv("LLAMA_USER_CB_COOLDOWN", "120"))


# Model routing configurations
MODEL_ROUTER_HEAVY_WORDS = int(os.getenv("MODEL_ROUTER_HEAVY_WORDS", "30"))
MODEL_ROUTER_HEAVY_TOKENS = int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "1000"))


# Intent detection threshold
SIM_THRESHOLD = float(os.getenv("SIM_THRESHOLD", "0.24"))

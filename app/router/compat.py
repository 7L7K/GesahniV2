"""Backward compatibility shims for app.router imports.

This module provides thin forwarders to maintain compatibility with
existing code that imports symbols from app.router.

These shims import from leaf modules only - no circular dependencies.
"""

# Import from leaf modules (safe, no circular imports)
# Import legacy functions that tests might expect
from app.gpt_client import ask_gpt

from .budget import get_remaining_budget
from .entrypoint import route_prompt
from .policy import (
    ALLOWED_GPT_MODELS,
    ALLOWED_LLAMA_MODELS,
    OLLAMA_TIMEOUT_MS,
    OPENAI_TIMEOUT_MS,
    ROUTER_BUDGET_MS,
)

# Legacy aliases that some tests might expect
ALLOWED_MODELS = ALLOWED_GPT_MODELS | ALLOWED_LLAMA_MODELS

# Additional legacy constants that might be expected
# (These would be imported from appropriate modules if they exist)
try:
    from .policy import (
        LLAMA_USER_CB_COOLDOWN,
        LLAMA_USER_CB_THRESHOLD,
        MODEL_ROUTER_HEAVY_TOKENS,
        MODEL_ROUTER_HEAVY_WORDS,
        SIM_THRESHOLD,
    )
except ImportError:
    # If these don't exist in policy, define reasonable defaults
    LLAMA_USER_CB_THRESHOLD = 3
    LLAMA_USER_CB_COOLDOWN = 120.0
    MODEL_ROUTER_HEAVY_WORDS = 30
    MODEL_ROUTER_HEAVY_TOKENS = 1000
    SIM_THRESHOLD = 0.24

# Export all the legacy symbols
__all__ = [
    # Core functions
    "route_prompt",
    "get_remaining_budget",
    "ask_gpt",
    # Model allowlists
    "ALLOWED_GPT_MODELS",
    "ALLOWED_LLAMA_MODELS",
    "ALLOWED_MODELS",
    # Timeout constants
    "OPENAI_TIMEOUT_MS",
    "OLLAMA_TIMEOUT_MS",
    # Budget constants
    "ROUTER_BUDGET_MS",
    # Circuit breaker settings
    "LLAMA_USER_CB_THRESHOLD",
    "LLAMA_USER_CB_COOLDOWN",
    # Model routing settings
    "MODEL_ROUTER_HEAVY_WORDS",
    "MODEL_ROUTER_HEAVY_TOKENS",
    "SIM_THRESHOLD",
]

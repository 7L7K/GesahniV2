"""Router package providing modular routing components.

This package contains the routing system components including:
- contracts: Lightweight router protocol definitions
- registry: Global router instance management
- entrypoint: Public routing API
- model_router: Concrete router implementation

All heavy imports are deferred to avoid circular dependencies.
"""

# Import registry from bootstrap location (neutral composition root)
from ..bootstrap.router_registry import get_router, set_router

# Import backward compatibility shims from compat module
from .compat import (
    route_prompt,
    get_remaining_budget,
    ALLOWED_GPT_MODELS,
    ALLOWED_LLAMA_MODELS,
    ALLOWED_MODELS,
    OPENAI_TIMEOUT_MS,
    OLLAMA_TIMEOUT_MS,
    ROUTER_BUDGET_MS,
    LLAMA_USER_CB_THRESHOLD,
    LLAMA_USER_CB_COOLDOWN,
    MODEL_ROUTER_HEAVY_WORDS,
    MODEL_ROUTER_HEAVY_TOKENS,
    SIM_THRESHOLD,
)

__all__ = [
    # Registry functions
    "get_router",
    "set_router",

    # Backward compatibility shims (from compat)
    "route_prompt",
    "get_remaining_budget",
    "ALLOWED_GPT_MODELS",
    "ALLOWED_LLAMA_MODELS",
    "ALLOWED_MODELS",
    "OPENAI_TIMEOUT_MS",
    "OLLAMA_TIMEOUT_MS",
    "ROUTER_BUDGET_MS",
    "LLAMA_USER_CB_THRESHOLD",
    "LLAMA_USER_CB_COOLDOWN",
    "MODEL_ROUTER_HEAVY_WORDS",
    "MODEL_ROUTER_HEAVY_TOKENS",
    "SIM_THRESHOLD",
]
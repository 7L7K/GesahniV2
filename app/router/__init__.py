"""Router package for model selection and routing logic."""

# Export what's available in this package
from .model_router import ModelRouter, RoutingDecision, model_router
from .rules_loader import get_router_rules, get_cached_router_rules
from .debug_flags import is_debug_routing_enabled, is_dry_run_mode, should_use_dry_run_response

# Import constants from the main router module to make them available
try:
    import sys
    import os
    # Import the router module directly to avoid circular imports
    sys.path.insert(0, os.path.dirname(__file__))
    import router as router_module

    OPENAI_TIMEOUT_MS = router_module.OPENAI_TIMEOUT_MS
    OLLAMA_TIMEOUT_MS = router_module.OLLAMA_TIMEOUT_MS
    route_prompt = router_module.route_prompt
    get_remaining_budget = router_module.get_remaining_budget
    ALLOWED_GPT_MODELS = router_module.ALLOWED_GPT_MODELS
    ALLOWED_LLAMA_MODELS = router_module.ALLOWED_LLAMA_MODELS
    __all__ = [
        "ModelRouter",
        "RoutingDecision",
        "model_router",
        "get_router_rules",
        "get_cached_router_rules",
        "is_debug_routing_enabled",
        "is_dry_run_mode",
        "should_use_dry_run_response",
        "OPENAI_TIMEOUT_MS",
        "OLLAMA_TIMEOUT_MS",
        "route_prompt",
        "get_remaining_budget",
        "ALLOWED_GPT_MODELS",
        "ALLOWED_LLAMA_MODELS",
    ]
except ImportError:
    # Fallback if circular import occurs - define constants directly
    import os
    OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
    OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))
    ALLOWED_GPT_MODELS = set(
        filter(
            None,
            os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(","),
        )
    )
    ALLOWED_LLAMA_MODELS = set(
        filter(
            None, os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(",")
        )
    )

    # Define fallback functions and values
    def get_remaining_budget(start_time: float) -> float:
        """Calculate remaining budget in seconds based on start time."""
        import time
        ROUTER_BUDGET_MS = int(os.getenv("ROUTER_BUDGET_MS", "7000"))
        elapsed_ms = (time.monotonic() - start_time) * 1000
        remaining_ms = max(0, ROUTER_BUDGET_MS - elapsed_ms)
        return remaining_ms / 1000  # Convert to seconds

    def route_prompt(prompt: str, user_id: str, **kwargs):
        """Stub route_prompt function for fallback."""
        raise NotImplementedError("route_prompt not available due to import error")

    # Re-export with fallback values
    __all__ = [
        "ModelRouter",
        "RoutingDecision",
        "model_router",
        "get_router_rules",
        "get_cached_router_rules",
        "is_debug_routing_enabled",
        "is_dry_run_mode",
        "should_use_dry_run_response",
        "OPENAI_TIMEOUT_MS",
        "OLLAMA_TIMEOUT_MS",
        "route_prompt",
        "get_remaining_budget",
        "ALLOWED_GPT_MODELS",
        "ALLOWED_LLAMA_MODELS",
    ]

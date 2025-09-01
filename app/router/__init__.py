"""Router package for model selection and routing logic."""

# Export what's available in this package
from .model_router import ModelRouter, RoutingDecision, model_router
from .rules_loader import get_router_rules, get_cached_router_rules
from .debug_flags import is_debug_routing_enabled, is_dry_run_mode, should_use_dry_run_response

# Import constants from the main router module to make them available
try:
    from ..router import OPENAI_TIMEOUT_MS, OLLAMA_TIMEOUT_MS, route_prompt
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
    ]
except ImportError:
    # Fallback if circular import occurs
    __all__ = [
        "ModelRouter",
        "RoutingDecision",
        "model_router",
        "get_router_rules",
        "get_cached_router_rules",
        "is_debug_routing_enabled",
        "is_dry_run_mode",
        "should_use_dry_run_response",
    ]

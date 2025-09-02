"""Router package for model selection and routing logic."""

# Export what's available in this package
# Temporarily disable problematic imports that cause circular dependencies
# from .model_router import ModelRouter, RoutingDecision, model_router
# from .rules_loader import get_router_rules, get_cached_router_rules
# from .debug_flags import is_debug_routing_enabled, is_dry_run_mode, should_use_dry_run_response

# Stub classes and functions for compatibility
class ModelRouter:
    pass

class RoutingDecision:
    pass

def model_router():
    pass

def get_router_rules():
    pass

def get_cached_router_rules():
    pass

def is_debug_routing_enabled():
    return False

def is_dry_run_mode():
    return False

def should_use_dry_run_response():
    return False

# Constants needed by API modules
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

# The router package provides configuration and utilities
# The main route_prompt function is imported directly from the main router module
# in app/main.py to avoid circular imports

def get_remaining_budget(start_time: float) -> float:
    """Calculate remaining budget - fallback stub"""
    return 0.0

# Provide route_prompt function for backward compatibility
# This will be set by the main module after importing
route_prompt = None

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
    "ALLOWED_GPT_MODELS",
    "ALLOWED_LLAMA_MODELS",
    "route_prompt",
    "get_remaining_budget",
]

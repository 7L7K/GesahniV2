"""Neutral composition root for router wiring.

This module centralizes router configuration and wiring decisions.
It can be imported in isolation without pulling in heavy dependencies.

Only used by create_app() - no other modules should import this.
"""
from __future__ import annotations

from typing import Optional

# Import Router protocol from bootstrap location
from .router_contracts import Router


_router: Optional[Router] = None


def set_router(router: Router) -> None:
    """Set the global router instance.

    This is intended to be called once during application startup.
    """
    global _router
    _router = router


def get_router() -> Router:
    """Return the registered router or raise RuntimeError if unset."""
    if _router is None:
        raise RuntimeError("Router has not been configured. Call set_router() first.")
    return _router


def create_model_router_adapter() -> Router:
    """Create a Router adapter for the ModelRouter.

    This function imports the ModelRouter only when called, avoiding
    import-time circular dependencies.
    """
    # Import inside function to avoid circular imports
    from app.router.model_router import model_router as model_router_instance

    class ModelRouterAdapter:
        """Adapter to make ModelRouter implement the Router protocol."""

        def __init__(self, model_router):
            self.model_router = model_router

        async def route_prompt(self, payload: dict) -> dict:
            """Implement Router protocol by delegating to ModelRouter."""
            # Extract parameters from payload
            prompt = payload.get("prompt", "")
            user_id = payload.get("user_id", "unknown")
            model_override = payload.get("model_override") or payload.get("model")
            stream = payload.get("stream", False)

            # For now, use simple intent detection
            intent = payload.get("intent", "general")

            # Estimate token count (simplified)
            tokens = len(prompt.split()) * 1.3  # Rough approximation

            # Route using the model router
            routing_decision = self.model_router.route_model(
                prompt=prompt,
                user_id=user_id,
                intent=intent,
                tokens=int(tokens),
                model_override=model_override,
                stream=stream,
            )

            # Convert RoutingDecision to dict response
            return {
                "vendor": routing_decision.vendor,
                "model": routing_decision.model,
                "reason": routing_decision.reason,
                "keyword_hit": routing_decision.keyword_hit,
                "stream": routing_decision.stream,
                "request_id": routing_decision.request_id,
            }

    return ModelRouterAdapter(model_router_instance)


def create_legacy_router_adapter() -> Router:
    """Create a Router adapter for the legacy router module.

    This function imports the legacy router only when called, avoiding
    import-time circular dependencies.
    """
    # Import inside function to avoid circular imports
    import importlib

    try:
        legacy = importlib.import_module("router")

        if hasattr(legacy, "route_prompt"):
            fn = getattr(legacy, "route_prompt")

            class LegacyRouterAdapter:
                """Adapter to make legacy router implement the Router protocol."""

                async def route_prompt(self, payload: dict) -> dict:
                    """Implement Router protocol by delegating to legacy router."""
                    return await fn(payload)

            return LegacyRouterAdapter()

    except Exception:
        pass

    raise RuntimeError("Legacy router not available or does not implement route_prompt")


def configure_default_router() -> None:
    """Configure the default router for the application.

    This function sets up the router that should be used by default.
    It prefers the ModelRouter but falls back to legacy router if needed.
    """
    try:
        # Try ModelRouter first
        router = create_model_router_adapter()
        set_router(router)
    except Exception:
        # Fall back to legacy router
        try:
            router = create_legacy_router_adapter()
            set_router(router)
        except Exception:
            raise RuntimeError("No suitable router implementation found")


def configure_router_by_name(name: str) -> None:
    """Configure router by name.

    Args:
        name: Router name ("model", "legacy", etc.)
    """
    if name == "model":
        router = create_model_router_adapter()
        set_router(router)
    elif name == "legacy":
        router = create_legacy_router_adapter()
        set_router(router)
    else:
        raise ValueError(f"Unknown router: {name}")

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

__all__ = [
    "get_router",
    "set_router",
]
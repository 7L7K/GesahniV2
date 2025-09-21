"""
Factory functions for creating service instances.

These factories provide pure functions that return service instances without any
lifecycle management. They are suitable for testing and direct instantiation.
"""

from __future__ import annotations

from .auth_store_tokens import TokenDAO


def make_token_store() -> TokenDAO:
    """
    Factory function to create a TokenDAO instance.

    This is a pure factory that returns a TokenDAO instance without any
    lifecycle management. Use this in tests or when you need direct control
    over the token store lifecycle.

    Returns:
        TokenDAO: A new TokenDAO instance
    """
    return TokenDAO()


__all__ = ["make_token_store"]

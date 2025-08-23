"""Test utilities for JWT token generation and authentication testing."""

import os
import time

import jwt


def mint_jwt_token(
    scopes: list[str] | None = None,
    sub: str = "test-user-123",
    ttl: int = 300,
    secret: str | None = None
) -> str:
    """
    Mint a JWT token for testing.

    Args:
        scopes: List of scopes to include in the token
        sub: Subject (user ID) for the token
        ttl: Time to live in seconds
        secret: JWT secret to use (defaults to JWT_SECRET env var)

    Returns:
        JWT token as string
    """
    if secret is None:
        secret = os.environ.get("JWT_SECRET", "test-secret-key")

    now = int(time.time())
    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + ttl,
    }

    if scopes is not None:
        payload["scopes"] = scopes

    return jwt.encode(payload, secret, algorithm="HS256")


def get_test_tokens():
    """
    Get a set of test tokens with different scopes for testing.

    Returns:
        Dict of token names to JWT tokens
    """
    return {
        "no_scopes": mint_jwt_token(scopes=[]),
        "user_profile": mint_jwt_token(scopes=["user:profile"]),
        "admin_read": mint_jwt_token(scopes=["admin:read"]),
        "admin_write": mint_jwt_token(scopes=["admin:write"]),
        "admin_full": mint_jwt_token(scopes=["admin"]),
        "mixed_scopes": mint_jwt_token(scopes=["user:profile", "admin:read"]),
    }

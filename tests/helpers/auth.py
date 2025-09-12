"""Test helpers for authentication using unified constants."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.auth.constants import JWT_ALG, JWT_AUD, JWT_ISS, JWT_SECRET


def mint_test_jwt(payload: dict[str, Any], ttl_seconds: int = 3600, token_type: str = "access") -> str:
    """Mint a test JWT using unified constants.

    Args:
        payload: JWT payload (will be augmented with standard claims)
        ttl_seconds: Token time-to-live in seconds
        token_type: Type of token ("access", "refresh", etc.)

    Returns:
        JWT token string
    """
    # Get JWT secret from environment or use test default
    secret = os.getenv("JWT_SECRET") or JWT_SECRET or "test-jwt-secret-key-for-testing-only"

    # Augment payload with standard claims
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=ttl_seconds)

    full_payload = {
        "iss": JWT_ISS,
        "aud": JWT_AUD,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": token_type,
        **payload
    }

    return jwt.encode(full_payload, secret, algorithm=JWT_ALG)


def mint_access_token(user_id: str, ttl_seconds: int = 3600, **extra_payload) -> str:
    """Mint a test access token for a user.

    Args:
        user_id: User ID to include in token
        ttl_seconds: Token time-to-live in seconds
        extra_payload: Additional payload data

    Returns:
        JWT access token string
    """
    payload = {"user_id": user_id, "sub": user_id, **extra_payload}
    return mint_test_jwt(payload, ttl_seconds, "access")


def mint_refresh_token(user_id: str, jti: str = None, ttl_seconds: int = 86400, **extra_payload) -> str:
    """Mint a test refresh token for a user.

    Args:
        user_id: User ID to include in token
        jti: JWT ID for token uniqueness
        ttl_seconds: Token time-to-live in seconds (default 24 hours)
        extra_payload: Additional payload data

    Returns:
        JWT refresh token string
    """
    payload = {"user_id": user_id, "sub": user_id, **extra_payload}
    if jti:
        payload["jti"] = jti
    return mint_test_jwt(payload, ttl_seconds, "refresh")

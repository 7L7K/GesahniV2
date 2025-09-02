"""
Token creation facade module.

This module provides a clean interface for creating JWT tokens,
with centralized TTL management and normalized claims handling.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt

# JWT configuration constants
ALGORITHM = os.getenv("JWT_ALGS", "HS256").split(",")[0].strip() or "HS256"
SECRET_KEY = os.getenv("JWT_SECRET")
JWT_ISS = os.getenv("JWT_ISS")
JWT_AUD = os.getenv("JWT_AUD")

# Token expiration times (fallback defaults)
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))

logger = logging.getLogger(__name__)


def _ensure_jwt_secret_present() -> None:
    """Raise a clear ValueError if JWT_SECRET is missing or insecure."""
    if not SECRET_KEY or not SECRET_KEY.strip():
        raise ValueError("JWT_SECRET environment variable must be set")
    if SECRET_KEY.strip().lower() in {
        "change-me",
        "default",
        "placeholder",
        "secret",
        "key",
    }:
        raise ValueError("JWT_SECRET cannot use insecure default values")


def _create_access_token_internal(
    data: dict, expires_delta: timedelta | None = None
) -> str:
    """Internal function to create a JWT access token with the given data.

    Args:
        data: Dictionary containing token claims
        expires_delta: Optional expiration delta (defaults to EXPIRE_MINUTES)

    Returns:
        JWT access token string
    """
    # Choose signing key/alg dynamically
    alg, key, kid = _select_signing_key()

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": uuid4().hex,
            "type": "access",
            "scopes": data.get("scopes", ["care:resident", "music:control", "chat:write"]),
        }
    )

    if JWT_ISS:
        to_encode["iss"] = JWT_ISS
    if JWT_AUD:
        to_encode["aud"] = JWT_AUD

    logger.debug(
        "auth.create_access_token",
        extra={
            "meta": {
                "user_id": data.get("sub"),
                "expires_at": expire.isoformat(),
                "jti": to_encode["jti"],
                "scopes": to_encode["scopes"],
            }
        },
    )

    headers = {"kid": kid} if kid else None
    return jwt.encode(to_encode, key, algorithm=alg, headers=headers)


def _create_refresh_token_internal(
    data: dict, expires_delta: timedelta | None = None
) -> str:
    """Internal function to create a JWT refresh token with the given data.

    Args:
        data: Dictionary containing token claims
        expires_delta: Optional expiration delta (defaults to REFRESH_EXPIRE_MINUTES)

    Returns:
        JWT refresh token string
    """
    # Choose signing key/alg dynamically
    alg, key, kid = _select_signing_key()

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": uuid4().hex,
            "type": "refresh",
            "scopes": data.get("scopes", ["care:resident", "music:control", "chat:write"]),
        }
    )

    if JWT_ISS:
        to_encode["iss"] = JWT_ISS
    if JWT_AUD:
        to_encode["aud"] = JWT_AUD

    logger.debug(
        "auth.create_refresh_token",
        extra={
            "meta": {
                "user_id": data.get("sub"),
                "expires_at": expire.isoformat(),
                "jti": to_encode["jti"],
                "scopes": to_encode["scopes"],
            }
        },
    )

    headers = {"kid": kid} if kid else None
    return jwt.encode(to_encode, key, algorithm=alg, headers=headers)


# Centralized TTL defaults (read once and convert to seconds)
def _get_access_ttl_seconds() -> int:
    """Get access token TTL in seconds from environment."""
    # First try JWT_ACCESS_TTL_SECONDS for direct seconds config
    if os.getenv("JWT_ACCESS_TTL_SECONDS"):
        # Default to 1800s (30 minutes) if the var is present but empty
        return int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1800"))
    # Fall back to JWT_EXPIRE_MINUTES converted to seconds
    minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
    return minutes * 60


def _get_refresh_ttl_seconds() -> int:
    """Get refresh token TTL in seconds from environment."""
    # First try JWT_REFRESH_TTL_SECONDS for direct seconds config
    if os.getenv("JWT_REFRESH_TTL_SECONDS"):
        # Default to 86400s (1 day) if the var is present but empty
        return int(os.getenv("JWT_REFRESH_TTL_SECONDS", "86400"))
    # Fall back to JWT_REFRESH_EXPIRE_MINUTES converted to seconds
    minutes = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))
    return minutes * 60


def _normalize_access_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """Normalize and complete access token claims."""
    normalized = claims.copy()

    # Ensure required claims are present
    if "sub" not in normalized and "user_id" in normalized:
        normalized["sub"] = normalized["user_id"]
    elif "user_id" not in normalized and "sub" in normalized:
        normalized["user_id"] = normalized["sub"]

    # Add standard claims
    normalized.setdefault("type", "access")
    normalized.setdefault("scopes", ["care:resident", "music:control", "chat:write"])

    # Add standard JWT claims that will be set by create_access_token
    # (iat, exp, jti will be added by the underlying implementation)

    return normalized


def _normalize_refresh_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """Normalize and complete refresh token claims."""
    normalized = claims.copy()

    # Ensure required claims are present
    if "sub" not in normalized and "user_id" in normalized:
        normalized["sub"] = normalized["user_id"]
    elif "user_id" not in normalized and "sub" in normalized:
        normalized["user_id"] = normalized["sub"]

    # Add standard claims
    normalized.setdefault("type", "refresh")
    normalized.setdefault("scopes", ["care:resident", "music:control", "chat:write"])

    # Ensure JTI is present for refresh tokens (required for revocation)
    if "jti" not in normalized:
        normalized["jti"] = uuid4().hex

    return normalized


def make_access(
    claims: dict[str, Any],
    *,
    ttl_s: int | None = None,
    alg: str | None = None,
    key: str | None = None,
    kid: str | None = None
) -> str:
    """
    Create an access token with normalized claims and centralized TTL handling.

    Args:
        claims: Dictionary containing token claims (must include "sub" or "user_id")
        ttl_s: Optional TTL in seconds (defaults to centralized TTL configuration)
        alg: Optional algorithm override (currently ignored, uses HS256)
        key: Optional key override (currently ignored, uses JWT_SECRET)
        kid: Optional key ID (currently ignored)

    Returns:
        JWT access token string
    """
    # Use centralized TTL if not provided
    if ttl_s is None:
        ttl_s = _get_access_ttl_seconds()

    # Normalize claims
    normalized_claims = _normalize_access_claims(claims)

    # Convert ttl_s to timedelta
    expires_delta = timedelta(seconds=ttl_s)

    return _create_access_token_internal(normalized_claims, expires_delta=expires_delta)


def make_refresh(
    claims: dict[str, Any],
    *,
    ttl_s: int | None = None,
    alg: str | None = None,
    key: str | None = None,
    kid: str | None = None
) -> str:
    """
    Create a refresh token with normalized claims and centralized TTL handling.

    Args:
        claims: Dictionary containing token claims (must include "sub" or "user_id")
        ttl_s: Optional TTL in seconds (defaults to centralized TTL configuration)
        alg: Optional algorithm override (currently ignored, uses HS256)
        key: Optional key override (currently ignored, uses JWT_SECRET)
        kid: Optional key ID (currently ignored)

    Returns:
        JWT refresh token string
    """
    # Use centralized TTL if not provided
    if ttl_s is None:
        ttl_s = _get_refresh_ttl_seconds()

    # Normalize claims
    normalized_claims = _normalize_refresh_claims(claims)

    # Convert ttl_s to timedelta
    expires_delta = timedelta(seconds=ttl_s)

    return _create_refresh_token_internal(
        normalized_claims, expires_delta=expires_delta
    )


def get_default_access_ttl() -> int:
    """Get the default access token TTL in seconds."""
    return _get_access_ttl_seconds()


def get_default_refresh_ttl() -> int:
    """Get the default refresh token TTL in seconds."""
    return _get_refresh_ttl_seconds()


# Public functions that maintain the same interface as the original auth.py functions
# DEPRECATED: Use make_access() and make_refresh() instead for better TTL management and claim normalization
import warnings


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token with the given data.

    DEPRECATED: Use make_access() instead for better TTL management and claim normalization.

    Args:
        data: Dictionary containing token claims
        expires_delta: Optional expiration delta (defaults to EXPIRE_MINUTES)

    Returns:
        JWT access token string
    """
    warnings.warn(
        "create_access_token is deprecated. Use make_access() instead for better TTL management and claim normalization.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _create_access_token_internal(data, expires_delta=expires_delta)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT refresh token with the given data.

    DEPRECATED: Use make_refresh() instead for better TTL management and claim normalization.

    Args:
        data: Dictionary containing token claims
        expires_delta: Optional expiration delta (defaults to REFRESH_EXPIRE_MINUTES)

    Returns:
        JWT refresh token string
    """
    warnings.warn(
        "create_refresh_token is deprecated. Use make_refresh() instead for better TTL management and claim normalization.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _create_refresh_token_internal(data, expires_delta=expires_delta)


# -----------------
# Key selection
# -----------------

def _select_signing_key() -> tuple[str, str, str | None]:
    """Select signing algorithm, key, and kid based on environment.

    Prefers RS/ES when JWT_PRIVATE_KEYS is provided; otherwise falls back to HS256.
    Returns (alg, key, kid).
    """
    # Try private keys for RS/ES
    try:
        import json

        priv = os.getenv("JWT_PRIVATE_KEYS")
        if priv:
            mapping = json.loads(priv)
            if isinstance(mapping, dict) and mapping:
                primary = os.getenv("JWT_PRIMARY_KID") or next(iter(mapping.keys()))
                pem = mapping.get(primary) or next(iter(mapping.values()))
                # Default alg preference from env JWT_ALGS sequence; else RS256
                algs = [a.strip() for a in (os.getenv("JWT_ALGS") or "RS256,HS256").split(",") if a.strip()]
                alg = next((a for a in algs if a in {"RS256", "ES256"}), "RS256")
                if pem:
                    return alg, pem, primary
    except Exception:
        pass
    # Fallback HS256
    # Get JWT secret dynamically to handle test environment changes
    try:
        from .api.auth import _jwt_secret

        secret = _jwt_secret()
    except Exception:
        secret = os.getenv("JWT_SECRET", "")
    alg = "HS256"
    return alg, secret, None

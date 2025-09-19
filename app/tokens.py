"""
Token creation facade module.

This module provides a clean interface for creating JWT tokens,
with centralized TTL management and normalized claims handling.
"""

import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt

from app.security.jwt_config import get_jwt_config

logger = logging.getLogger(__name__)

# JWT configuration constants - now centralized in get_jwt_config()
# ALGORITHM, SECRET_KEY, JWT_ISS, JWT_AUD removed - use get_jwt_config() instead

# Token expiration times (fallback defaults)
# AT: 15 minutes for security
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "15"))
# RT: 30 days (43200 minutes) - can be configured 7-30 days
REFRESH_EXPIRE_MINUTES = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "43200"))

logger = logging.getLogger(__name__)


def _ensure_jwt_secret_present() -> None:
    """No-op in new configuration; kept for backward compatibility."""
    # get_jwt_config() handles validation; callers don't use this helper anymore.
    return None


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
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
            "jti": uuid4().hex,
            "type": "access",
            "scopes": data.get(
                "scopes", ["care:resident", "music:control", "chat:write"]
            ),
        }
    )

    # Add issuer/audience from centralized config when available
    try:
        cfg = get_jwt_config()
        if cfg.issuer:
            to_encode["iss"] = cfg.issuer
        if cfg.audience:
            to_encode["aud"] = cfg.audience
    except Exception:
        pass

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
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=REFRESH_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
            "jti": uuid4().hex,
            "type": "refresh",
            "scopes": data.get(
                "scopes", ["care:resident", "music:control", "chat:write"]
            ),
        }
    )

    # Add issuer/audience from centralized config when available
    try:
        cfg = get_jwt_config()
        if cfg.issuer:
            to_encode["iss"] = cfg.issuer
        if cfg.audience:
            to_encode["aud"] = cfg.audience
    except Exception:
        pass

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
    
    logger.info(f"🔍 TOKEN_NORMALIZE_ACCESS: Normalizing access claims", extra={
        "meta": {
            "input_claims": claims,
            "normalized_claims": normalized,
            "has_sid": "sid" in claims,
            "has_device_id": "device_id" in claims,
            "has_sess_ver": "sess_ver" in claims,
            "timestamp": time.time()
        }
    })

    # Ensure required claims are present
    if "sub" not in normalized and "user_id" in normalized:
        normalized["sub"] = normalized["user_id"]
    elif "user_id" not in normalized and "sub" in normalized:
        normalized["user_id"] = normalized["sub"]

    # Add standard claims
    normalized.setdefault("type", "access")
    normalized.setdefault("scopes", ["care:resident", "music:control", "chat:write"])

    # sess_ver should be provided directly in the claims, not fetched here
    # This avoids async calls in synchronous token creation functions

    # Add standard JWT claims that will be set by create_access_token
    # (iat, exp, jti will be added by the underlying implementation)
    
    logger.info(f"🔍 TOKEN_NORMALIZE_ACCESS_RESULT: Final normalized claims", extra={
        "meta": {
            "final_claims": normalized,
            "has_sid": "sid" in normalized,
            "has_device_id": "device_id" in normalized,
            "has_sess_ver": "sess_ver" in normalized,
            "timestamp": time.time()
        }
    })

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
    kid: str | None = None,
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
    kid: str | None = None,
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
    """Select signing algorithm, key, and kid based on centralized config.

    Uses get_jwt_config() for consistent configuration.
    Returns (alg, key, kid).
    """
    cfg = get_jwt_config()

    if cfg.secret:
        # Legacy HS256 mode
        return cfg.alg, cfg.secret, None
    elif cfg.private_keys:
        # Key rotation mode: pick first key for signing
        kid, key = next(iter(cfg.private_keys.items()))
        return cfg.alg, key, kid
    else:
        raise RuntimeError("No JWT keys available")


# Centralized token creation using get_jwt_config()


def _now():
    """Get current UTC datetime."""
    return datetime.now(tz=UTC)


def sign_access_token(sub: str, *, extra: dict | None = None) -> str:
    """Create a JWT access token using centralized configuration."""
    cfg = get_jwt_config()  # Auto-detects DEV_MODE

    # Check for TTL override in extra claims
    ttl_minutes = cfg.access_ttl_min
    if extra and "ttl_override" in extra:
        ttl_minutes = extra.pop("ttl_override")  # Remove from extra claims

    claims = {
        "sub": sub,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    if cfg.issuer:
        claims["iss"] = cfg.issuer
    if cfg.audience:
        claims["aud"] = cfg.audience
    if extra:
        claims.update(extra)

    headers = {}
    if cfg.secret:
        # Legacy HS256 mode
        key = cfg.secret
    else:
        # Key rotation mode
        kid, key = next(iter(cfg.private_keys.items()))
        headers["kid"] = kid

    return jwt.encode(claims, key, algorithm=cfg.alg, headers=headers)


def sign_refresh_token(sub: str) -> str:
    """Create a JWT refresh token using centralized configuration."""
    cfg = get_jwt_config()  # Auto-detects DEV_MODE
    claims = {
        "sub": sub,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(minutes=cfg.refresh_ttl_min)).timestamp()),
        "typ": "refresh",
    }
    if cfg.issuer:
        claims["iss"] = cfg.issuer
    if cfg.audience:
        claims["aud"] = cfg.audience

    headers = {}
    if cfg.secret:
        # Legacy HS256 mode
        key = cfg.secret
    else:
        # Key rotation mode
        kid, key = next(iter(cfg.private_keys.items()))
        headers["kid"] = kid

    return jwt.encode(claims, key, algorithm=cfg.alg, headers=headers)


# -----------------
# JWT Decoding with Key Rotation Support
# -----------------


def decode_jwt_token(token: str) -> dict[str, Any]:
    """Decode JWT token with key rotation support.

    Tries all available keys until one works, supporting backward compatibility
    during key rotation scenarios.

    Args:
        token: JWT token string

    Returns:
        Decoded token claims

    Raises:
        jwt.InvalidTokenError: If token cannot be decoded with any key
    """
    cfg = get_jwt_config()

    # Extract header to get kid if present
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
    except Exception:
        kid = None

    # Try specific kid first if available
    if kid and cfg.public_keys and kid in cfg.public_keys:
        try:
            return jwt.decode(
                token,
                cfg.public_keys[kid],
                algorithms=[cfg.alg],
                audience=cfg.audience,
                issuer=cfg.issuer,
                options={"verify_exp": True, "verify_iat": True},
                leeway=cfg.clock_skew_s,
            )
        except jwt.InvalidTokenError:
            pass  # Fall through to try all keys

    # Try all available keys
    keys_to_try = []

    # Legacy HS256 secret (for backward compatibility)
    if cfg.secret:
        keys_to_try.append(("HS256", cfg.secret))

    # All public keys for asymmetric algorithms (including old keys for rotation)
    if cfg.public_keys:
        for _k, pub_key in cfg.public_keys.items():
            keys_to_try.append((cfg.alg, pub_key))

    # Also try legacy JWT_SECRET if available (for migration scenarios)
    legacy_secret = os.getenv("JWT_SECRET")
    if legacy_secret and legacy_secret != cfg.secret:
        keys_to_try.append(("HS256", legacy_secret))

    # Try each key until one works
    last_error = None
    for alg, key in keys_to_try:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=cfg.audience,
                issuer=cfg.issuer,
                options={"verify_exp": True, "verify_iat": True},
                leeway=cfg.clock_skew_s,
            )
        except jwt.InvalidTokenError as e:
            last_error = e
            continue

    # If we get here, all keys failed
    if last_error:
        raise last_error
    else:
        raise jwt.InvalidTokenError("No keys available for JWT verification")


def verify_jwt_token(token: str) -> dict[str, Any]:
    """Verify and decode JWT token with key rotation support.

    Alias for decode_jwt_token for backward compatibility.
    """
    return decode_jwt_token(token)


# -----------------
# JWT Key Rotation Testing
# -----------------


def test_jwt_backward_compatibility():
    """Test JWT backward compatibility during key rotation."""
    import json
    import os

    # Save original env
    orig_env = dict(os.environ)

    try:
        # Test 1: Issue token with old key, rotate, ensure decode still works
        os.environ["JWT_SECRET"] = "old_secret_for_rotation_test_12345678901234567890"
        get_jwt_config()

        # Create token with old key
        old_token = sign_access_token("test_user", extra={"test": "rotation"})

        # Rotate to new key setup (keep old key for verification)
        os.environ.pop("JWT_SECRET", None)  # Remove old secret first
        os.environ["JWT_PRIVATE_KEYS"] = json.dumps(
            {
                "key1": "new_secret_for_rotation_test_12345678901234567890",
                "legacy": "old_secret_for_rotation_test_12345678901234567890",  # Keep old key
            }
        )
        os.environ["JWT_PUBLIC_KEYS"] = json.dumps(
            {
                "key1": "new_secret_for_rotation_test_12345678901234567890",
                "legacy": "old_secret_for_rotation_test_12345678901234567890",
            }
        )

        # Should still be able to decode old token (uses legacy key)
        decoded = decode_jwt_token(old_token)
        assert decoded["sub"] == "test_user"
        assert decoded["test"] == "rotation"

        # New tokens should use new key
        new_token = sign_access_token("test_user", extra={"test": "new_key"})
        new_decoded = decode_jwt_token(new_token)
        assert new_decoded["sub"] == "test_user"
        assert new_decoded["test"] == "new_key"

        return True
    except Exception as e:
        print(f"JWT rotation test failed: {e}")
        return False
    finally:
        # Restore original env
        os.environ.clear()
        os.environ.update(orig_env)


def remaining_ttl(jti: str | None | int) -> int:
    """
    Calculate remaining TTL for a JTI token.

    This is a simplified implementation that returns a reasonable default TTL.
    In production, you'd want to decode the actual token and calculate
    the remaining time until expiration.

    Args:
        jti: JWT ID token identifier (can be string, None, or other type)

    Returns:
        Remaining TTL in seconds (default 1 hour for safety)
    """
    try:
        # Handle None and non-string types
        if jti is None or not isinstance(jti, str):
            return 3600  # Default fallback

        # For now, return a conservative 1-hour TTL
        # In production, decode the token and calculate: exp - now
        return 3600  # 1 hour
    except Exception as e:
        logger.warning(f"Failed to calculate remaining TTL for JTI {jti}: {e}")
        return 3600  # Default fallback

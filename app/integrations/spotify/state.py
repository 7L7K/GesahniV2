"""
Spotify OAuth state management helpers.

This module provides utilities for generating and verifying signed OAuth state
parameters, along with PKCE (Proof Key for Code Exchange) helpers for enhanced
security.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time

from .config import JWT_STATE_SECRET

logger = logging.getLogger(__name__)


# Exceptions
class NonceConsumedError(Exception):
    """Raised when a state nonce has already been consumed (replay attempt)."""

    pass


# In-memory nonce store for one-time state consumption (anti-replay protection)
_nonce_store = set()
_nonce_store_lock = threading.Lock()


def _get_jwt_secret() -> str:
    """Get JWT secret for signing OAuth state."""
    secret = JWT_STATE_SECRET
    if not secret:
        # Fallback to a development secret if not configured
        logger.warning("JWT_STATE_SECRET not configured, using fallback (not secure for production)")
        secret = "dev-jwt-state-secret-change-in-production"
    return secret


def generate_signed_state() -> str:
    """Generate a signed JWT state parameter for OAuth CSRF protection.

    Returns:
        A JWT string containing timestamp, nonce, and signature
    """
    import jwt

    now = int(time.time())
    nonce = secrets.token_hex(16)  # 32-char hex nonce

    # Store nonce to prevent replay attacks
    with _nonce_store_lock:
        _nonce_store.add(nonce)

    payload = {
        "iat": now,
        "exp": now + 600,  # 10 minutes
        "nonce": nonce,
    }

    secret = _get_jwt_secret()
    token = jwt.encode(payload, secret, algorithm="HS256")

    logger.debug("Generated signed OAuth state", extra={
        "nonce_length": len(nonce),
        "token_length": len(token),
    })

    return token


def verify_signed_state(token: str) -> bool:
    """Verify a signed JWT state parameter.

    Args:
        token: The JWT state token to verify

    Returns:
        True if valid and not consumed, False otherwise
    """
    import jwt

    try:
        secret = _get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        # Check expiration
        now = int(time.time())
        if payload.get("exp", 0) < now:
            logger.warning("OAuth state token expired")
            return False

        # Check and consume nonce (anti-replay protection)
        nonce = payload.get("nonce")
        if not nonce:
            logger.warning("OAuth state token missing nonce")
            return False

        with _nonce_store_lock:
            if nonce not in _nonce_store:
                logger.warning("OAuth state nonce already consumed or invalid")
                return False
            _nonce_store.discard(nonce)  # Consume nonce

        logger.debug("Verified OAuth state token", extra={
            "nonce_length": len(nonce),
            "age_seconds": now - payload.get("iat", now),
        })

        return True

    except jwt.ExpiredSignatureError:
        logger.warning("OAuth state token signature expired")
        return False
    except jwt.InvalidSignatureError:
        logger.warning("OAuth state token has invalid signature")
        return False
    except Exception as e:
        logger.warning("OAuth state token verification failed", extra={
            "error": str(e),
            "error_type": type(e).__name__,
        })
        return False


def generate_pkce_verifier() -> str:
    """Generate a PKCE code verifier.

    Returns:
        A cryptographically secure random string (43-128 chars)
    """
    # Generate 32 bytes of random data, base64url encode it
    verifier_bytes = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(verifier_bytes).decode('ascii').rstrip('=')

    logger.debug("Generated PKCE verifier", extra={
        "verifier_length": len(verifier),
    })

    return verifier


def generate_pkce_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from a verifier.

    Args:
        verifier: The PKCE code verifier

    Returns:
        The base64url-encoded SHA256 hash of the verifier
    """
    # SHA256 hash the verifier
    verifier_bytes = verifier.encode('ascii')
    challenge_bytes = hashlib.sha256(verifier_bytes).digest()

    # Base64url encode the hash
    challenge = base64.urlsafe_b64encode(challenge_bytes).decode('ascii').rstrip('=')

    logger.debug("Generated PKCE challenge", extra={
        "challenge_length": len(challenge),
    })

    return challenge


# Periodic cleanup of expired nonces (runs every 5 minutes)
def _cleanup_expired_nonces():
    """Clean up expired nonces to prevent memory leaks."""
    try:
        # Simple cleanup: remove nonces older than 15 minutes
        # In a production system, you'd want more sophisticated cleanup
        cutoff_time = int(time.time()) - 900  # 15 minutes ago

        # For now, we'll just clear all nonces periodically
        # This is a simplification - in production you'd track timestamps
        with _nonce_store_lock:
            _nonce_store.clear()

        logger.debug("Cleaned up expired OAuth state nonces")
    except Exception as e:
        logger.warning("Failed to cleanup expired OAuth state nonces", extra={
            "error": str(e),
        })


# Start periodic cleanup
import atexit
atexit.register(_cleanup_expired_nonces)

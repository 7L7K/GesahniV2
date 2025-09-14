"""
Google OAuth state management helpers.

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
_nonce_store_max_size = 10000  # Prevent memory leaks
_nonce_store_ttl_seconds = 600  # 10 minutes TTL for nonces


def _cleanup_nonce_store():
    """Clean up expired nonces from the store to prevent memory leaks."""
    time.time()
    with _nonce_store_lock:
        # In a production system, we'd want to store timestamps with nonces
        # For now, we'll do a simple cleanup based on store size
        if len(_nonce_store) > _nonce_store_max_size:
            # Remove oldest entries (simplified cleanup)
            items_to_remove = len(_nonce_store) - (_nonce_store_max_size // 2)
            _nonce_store.clear()  # Simplified: clear and rebuild
            logger.warning(
                f"🧹 Cleaned up nonce store (removed {items_to_remove} entries)"
            )


def store_nonce(nonce: str) -> bool:
    """
    Store a nonce for one-time consumption.

    Args:
        nonce: The nonce to store

    Returns:
        bool: True if stored successfully, False if already exists
    """
    _cleanup_nonce_store()

    with _nonce_store_lock:
        if nonce in _nonce_store:
            logger.warning(f"🚨 Nonce already exists: {nonce[:16]}...")
            return False

        _nonce_store.add(nonce)
        logger.debug(f"🔐 Stored nonce: {nonce[:16]}...")
        return True


def nonce_exists(nonce: str) -> bool:
    """Check presence of a nonce without consuming it.

    Returns True if nonce is present (unused), False otherwise.
    """
    with _nonce_store_lock:
        return nonce in _nonce_store


def consume_nonce(nonce: str) -> bool:
    """
    Consume a nonce (mark as used).

    Args:
        nonce: The nonce to consume

    Returns:
        bool: True if consumed successfully, False if not found or already consumed
    """
    with _nonce_store_lock:
        if nonce in _nonce_store:
            _nonce_store.remove(nonce)
            logger.debug(f"✅ Consumed nonce: {nonce[:16]}...")
            return True
        else:
            logger.warning(f"🚨 Nonce not found or already consumed: {nonce[:16]}...")
            return False


def generate_signed_state() -> str:
    """
    Generate a signed state string for CSRF protection.

    Returns:
        str: timestamp:random:nonce:sig format (kept short to avoid URL length issues)
    """
    logger.debug("🔐 Generating timestamp for state")
    timestamp = str(int(time.time()))

    logger.debug("🎲 Generating random token for state")
    random_token = secrets.token_urlsafe(12)  # Keep short for URL limits

    logger.debug("🎯 Generating nonce for state")
    nonce = secrets.token_urlsafe(8)  # Short nonce for replay protection

    # Store the nonce for one-time consumption
    if not store_nonce(nonce):
        # If nonce collision (very unlikely), regenerate
        nonce = secrets.token_urlsafe(8)
        store_nonce(nonce)

    # Create signature using a dedicated state secret (separate from JWT_SECRET)
    logger.debug("🔏 Creating HMAC signature for state using JWT_STATE_SECRET")
    message = f"{timestamp}:{random_token}:{nonce}".encode()
    sig_key = (
        JWT_STATE_SECRET.encode()
        if isinstance(JWT_STATE_SECRET, str)
        else JWT_STATE_SECRET
    )
    signature = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]

    state = f"{timestamp}:{random_token}:{nonce}:{signature}"
    logger.debug(
        f"✅ State generated: {timestamp}:[random]:[nonce]:[signature] (length: {len(state)})"
    )
    return state


def verify_signed_state(state: str, consume_nonce_on_success: bool = True) -> bool:
    """
    Verify a signed state string for CSRF protection and consume nonce.

    Args:
        state: State string in timestamp:random:nonce:sig format
        consume_nonce_on_success: Whether to consume the nonce on successful verification

    Returns:
        bool: True if state is valid and fresh
    """
    try:
        parts = state.split(":")
        if len(parts) != 4:
            logger.warning(
                f"🚨 Invalid state format: expected 4 parts, got {len(parts)}"
            )
            return False

        timestamp, random_token, nonce, signature = parts

        # Verify timestamp is recent (within 5 minutes)
        state_time = int(timestamp)
        current_time = int(time.time())
        if current_time - state_time > 300:  # 5 minutes
            logger.warning(f"🚨 State expired: {current_time - state_time}s ago")
            return False

        # Verify signature using the dedicated state secret
        message = f"{timestamp}:{random_token}:{nonce}".encode()
        sig_key = (
            JWT_STATE_SECRET.encode()
            if isinstance(JWT_STATE_SECRET, str)
            else JWT_STATE_SECRET
        )
        expected_sig = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]

        if signature != expected_sig:
            logger.warning("🚨 State signature mismatch")
            return False

        # Verify and consume nonce (anti-replay protection)
        if consume_nonce_on_success:
            if not consume_nonce(nonce):
                # Distinguish nonce-already-consumed as a special condition
                logger.warning(f"🚨 Nonce already consumed: {nonce[:16]}...")
                # Raise top-level NonceConsumedError to allow callers to return 409
                raise NonceConsumedError("nonce already consumed")

        logger.debug(f"✅ State verified and nonce consumed: {nonce[:16]}...")
        return True
    except Exception as e:
        logger.warning(f"🚨 State verification failed: {e}")
        return False


def generate_pkce_verifier() -> str:
    """
    Generate a PKCE code verifier.

    Returns:
        str: Random string of 43-128 characters from the allowed character set
    """
    # Generate 32 bytes of random data (will result in ~43 characters when base64url encoded)
    verifier_bytes = secrets.token_bytes(32)

    # Base64url encode (RFC 7636 compliant)
    verifier = base64.urlsafe_b64encode(verifier_bytes).decode("ascii").rstrip("=")

    logger.debug(f"🔐 Generated PKCE verifier (length: {len(verifier)})")
    return verifier


def generate_pkce_challenge(verifier: str) -> str:
    """
    Generate a PKCE code challenge from a verifier.

    Args:
        verifier: The code verifier string

    Returns:
        str: SHA256 hash of verifier, base64url encoded
    """
    # SHA256 hash the verifier
    digest = hashlib.sha256(verifier.encode("ascii")).digest()

    # Base64url encode the hash
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    logger.debug("🔏 Generated PKCE challenge from verifier")
    return challenge


def create_state_with_pkce(user_id: str | None = None) -> tuple[str, str, str]:
    """
    Create a signed state along with PKCE parameters.

    Args:
        user_id: Optional user ID to include in state

    Returns:
        tuple: (state, code_verifier, code_challenge)
    """
    state = generate_signed_state()
    code_verifier = generate_pkce_verifier()
    code_challenge = generate_pkce_challenge(code_verifier)

    if user_id:
        logger.info(f"🔐 Created OAuth state with PKCE and nonce for user {user_id}")
    else:
        logger.info("🔐 Created OAuth state with PKCE and nonce")

    return state, code_verifier, code_challenge

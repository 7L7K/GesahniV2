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
import time
from typing import Optional

from .config import JWT_STATE_SECRET

logger = logging.getLogger(__name__)


def generate_signed_state() -> str:
    """
    Generate a signed state string for CSRF protection.

    Returns:
        str: timestamp:random:sig format (kept short to avoid URL length issues)
    """
    logger.debug("🔐 Generating timestamp for state")
    timestamp = str(int(time.time()))

    logger.debug("🎲 Generating random token for state")
    random_token = secrets.token_urlsafe(16)  # Reduced from 32 to 16 for shorter state

    # Create signature using a dedicated state secret (separate from JWT_SECRET)
    logger.debug("🔏 Creating HMAC signature for state using JWT_STATE_SECRET")
    message = f"{timestamp}:{random_token}".encode()
    sig_key = (
        JWT_STATE_SECRET.encode()
        if isinstance(JWT_STATE_SECRET, str)
        else JWT_STATE_SECRET
    )
    signature = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]

    state = f"{timestamp}:{random_token}:{signature}"
    logger.debug(
        f"✅ State generated: {timestamp}:[random]:[signature] (length: {len(state)})"
    )
    return state


def verify_signed_state(state: str) -> bool:
    """
    Verify a signed state string for CSRF protection.

    Args:
        state: State string in timestamp:random:sig format

    Returns:
        bool: True if state is valid and fresh
    """
    try:
        parts = state.split(":")
        if len(parts) != 3:
            return False

        timestamp, random_token, signature = parts

        # Verify timestamp is recent (within 5 minutes)
        state_time = int(timestamp)
        current_time = int(time.time())
        if current_time - state_time > 300:  # 5 minutes
            return False

        # Verify signature using the dedicated state secret
        message = f"{timestamp}:{random_token}".encode()
        sig_key = (
            JWT_STATE_SECRET.encode()
            if isinstance(JWT_STATE_SECRET, str)
            else JWT_STATE_SECRET
        )
        expected_sig = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]

        return signature == expected_sig
    except Exception:
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
    verifier = base64.urlsafe_b64encode(verifier_bytes).decode('ascii').rstrip('=')

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
    digest = hashlib.sha256(verifier.encode('ascii')).digest()

    # Base64url encode the hash
    challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

    logger.debug(f"🔏 Generated PKCE challenge from verifier")
    return challenge


def create_state_with_pkce(user_id: Optional[str] = None) -> tuple[str, str, str]:
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
        logger.info(f"🔐 Created OAuth state with PKCE for user {user_id}")
    else:
        logger.info("🔐 Created OAuth state with PKCE")

    return state, code_verifier, code_challenge

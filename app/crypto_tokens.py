from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(kms_key: str) -> bytes:
    # Derive 32-byte key then base64-url encode for Fernet
    digest = hashlib.sha256(kms_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    kms = os.getenv("TOKENS_KMS_KEY", "")
    if not kms:
        raise ValueError("TOKENS_KMS_KEY not configured")
    key = _derive_fernet_key(kms)
    return Fernet(key)


def encrypt_token(plain: str) -> bytes:
    """Encrypt a plaintext token and return the raw ciphertext bytes."""
    f = _get_fernet()
    token_bytes = plain.encode("utf-8")
    ct = f.encrypt(token_bytes)
    return ct


def decrypt_token(blob: bytes) -> str:
    """Decrypt ciphertext bytes and return plaintext string.

    Raises InvalidToken when decryption fails.
    """
    f = _get_fernet()
    try:
        pt = f.decrypt(blob)
    except InvalidToken:
        raise
    return pt.decode("utf-8")



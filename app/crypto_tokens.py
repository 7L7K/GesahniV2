from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Key configuration
KMS_KEY = os.getenv("TOKENS_KMS_KEY")
KMS_KEY_ID = os.getenv("TOKENS_KMS_KEY_ID", "dev-1")


def base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def base64url_decode(data: str) -> bytes:
    """Decode base64url string to bytes."""
    # Add padding
    pad = -len(data) % 4
    if pad:
        data += "=" * pad
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def aead_encrypt(key: str, nonce: bytes, plaintext: bytes) -> bytes:
    """Encrypt plaintext using AES-GCM."""
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    aesgcm = AESGCM(key_bytes)
    return aesgcm.encrypt(nonce, plaintext, None)


def aead_decrypt(key: str, nonce: bytes, ciphertext: bytes) -> bytes:
    """Decrypt ciphertext using AES-GCM."""
    key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
    aesgcm = AESGCM(key_bytes)
    return aesgcm.decrypt(nonce, ciphertext, None)


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


def encrypt_token(plain: str) -> str:
    """Encrypt a plaintext token and return base64url-encoded ciphertext."""
    if not KMS_KEY:
        raise ValueError("TOKENS_KMS_KEY not configured")

    nonce = os.urandom(12)
    ct = aead_encrypt(KMS_KEY, nonce, plain.encode())
    envelope = json.dumps({
        "kid": KMS_KEY_ID,
        "n": base64url_encode(nonce),
        "ct": base64url_encode(ct),
    }).encode()
    return base64url_encode(envelope)


def decrypt_token(cipher: str) -> str:
    """Decrypt base64url-encoded ciphertext and return plaintext string.

    Raises InvalidToken when decryption fails.
    """
    if not KMS_KEY:
        raise ValueError("TOKENS_KMS_KEY not configured")

    try:
        env = json.loads(base64url_decode(cipher))
        # You could branch by env["kid"] here when rotating keys
        nonce = base64url_decode(env["n"])
        ct = base64url_decode(env["ct"])
        pt = aead_decrypt(KMS_KEY, nonce, ct)
        return pt.decode()
    except Exception:
        raise InvalidToken("Decryption failed")


# Legacy Fernet-based functions for backward compatibility
def encrypt_token_legacy(plain: str) -> bytes:
    """Encrypt a plaintext token and return the raw ciphertext bytes (legacy Fernet)."""
    f = _get_fernet()
    token_bytes = plain.encode("utf-8")
    ct = f.encrypt(token_bytes)
    return ct


def decrypt_token_legacy(blob: bytes) -> str:
    """Decrypt ciphertext bytes and return plaintext string (legacy Fernet).

    Raises InvalidToken when decryption fails.
    """
    f = _get_fernet()
    try:
        pt = f.decrypt(blob)
    except InvalidToken:
        raise
    return pt.decode("utf-8")

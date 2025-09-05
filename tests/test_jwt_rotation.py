"""Test JWT key rotation and backward compatibility."""
import json
import os
import pytest
from app.tokens import sign_access_token, decode_jwt_token, test_jwt_backward_compatibility
from app.security.jwt_config import get_jwt_config


def test_jwt_rotation_backward_compat():
    """Test that old tokens remain valid during key rotation and new tokens use new alg."""
    # Save original env
    orig_env = dict(os.environ)

    try:
        # Test 1: Issue token with old key, rotate, ensure decode still works
        os.environ["JWT_SECRET"] = "old_secret_for_rotation_test_12345678901234567890"
        old_cfg = get_jwt_config()

        # Create token with old key
        old_token = sign_access_token("test_user", extra={"test": "rotation"})

        # Rotate to new key setup (keep old key for verification)
        os.environ["JWT_PRIVATE_KEYS"] = json.dumps({
            "key1": "new_secret_for_rotation_test_12345678901234567890",
            "key2": "old_secret_for_rotation_test_12345678901234567890"  # Keep old key for verification
        })
        os.environ["JWT_PUBLIC_KEYS"] = json.dumps({
            "key1": "new_secret_for_rotation_test_12345678901234567890",
            "key2": "old_secret_for_rotation_test_12345678901234567890"
        })
        os.environ.pop("JWT_SECRET", None)  # Remove old secret

        # Should still be able to decode old token (uses key2)
        decoded = decode_jwt_token(old_token)
        assert decoded["sub"] == "test_user"
        assert decoded["test"] == "rotation"

        # New tokens should work (uses key1 for signing)
        new_token = sign_access_token("test_user", extra={"test": "new_key"})
        new_decoded = decode_jwt_token(new_token)
        assert new_decoded["sub"] == "test_user"
        assert new_decoded["test"] == "new_key"

    finally:
        # Restore original env
        os.environ.clear()
        os.environ.update(orig_env)


def test_jwt_rotation_hs256_to_hs256():
    """Test HS256 to HS256 key rotation."""
    orig_env = dict(os.environ)

    try:
        # Start with legacy secret
        os.environ["JWT_SECRET"] = "legacy_secret_12345678901234567890123456789012"
        old_token = sign_access_token("user1", extra={"version": "old"})

        # Rotate to key-based HS256 (keep old key for verification)
        os.environ["JWT_PRIVATE_KEYS"] = json.dumps({
            "key1": "new_secret_1234567890123456789012345678901234567890",
            "legacy": "legacy_secret_12345678901234567890123456789012"  # Keep old key
        })
        os.environ["JWT_PUBLIC_KEYS"] = json.dumps({
            "key1": "new_secret_1234567890123456789012345678901234567890",
            "legacy": "legacy_secret_12345678901234567890123456789012"
        })
        os.environ.pop("JWT_SECRET", None)

        # Old token should still decode (uses legacy key)
        decoded_old = decode_jwt_token(old_token)
        assert decoded_old["sub"] == "user1"
        assert decoded_old["version"] == "old"

        # New token should work (uses key1 for signing)
        new_token = sign_access_token("user1", extra={"version": "new"})
        decoded_new = decode_jwt_token(new_token)
        assert decoded_new["sub"] == "user1"
        assert decoded_new["version"] == "new"

    finally:
        os.environ.clear()
        os.environ.update(orig_env)


def test_jwt_rotation_multiple_keys():
    """Test JWT with multiple keys (simulating rotation scenario)."""
    orig_env = dict(os.environ)

    try:
        # Configure multiple keys (simulating rotation) - remove any existing JWT_SECRET first
        os.environ.pop("JWT_SECRET", None)
        os.environ["JWT_PRIVATE_KEYS"] = json.dumps({
            "key1": "old_secret_1234567890123456789012345678901234567890",
            "key2": "new_secret_1234567890123456789012345678901234567890"
        })
        os.environ["JWT_PUBLIC_KEYS"] = json.dumps({
            "key1": "old_secret_1234567890123456789012345678901234567890",
            "key2": "new_secret_1234567890123456789012345678901234567890"
        })

        # Create token (uses first key for signing - key1)
        token = sign_access_token("test_user", extra={"key_test": True})

        # Should decode successfully
        decoded = decode_jwt_token(token)
        assert decoded["sub"] == "test_user"
        assert decoded["key_test"] is True

    finally:
        os.environ.clear()
        os.environ.update(orig_env)


def test_jwt_rotation_integration():
    """Integration test using the built-in test function."""
    result = test_jwt_backward_compatibility()
    assert result is True

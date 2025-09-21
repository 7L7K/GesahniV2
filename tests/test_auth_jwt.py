"""
Tests for JWT claims building and UUID-only sub enforcement.
"""

import pytest
import uuid
from app.auth.jwt import (
    build_claims,
    build_claims_with_legacy_support,
    is_uuid_sub,
    get_user_uuid_from_claims,
    get_legacy_alias_from_claims,
    track_legacy_resolution,
    get_legacy_resolution_count,
)


class TestBuildClaims:
    """Test JWT claims building with UUID-only sub enforcement."""

    def test_build_claims_with_uuid_user_id(self):
        """Test building claims with UUID user_id."""
        user_uuid = str(uuid.uuid4())
        claims = build_claims(user_uuid)
        
        assert claims["sub"] == user_uuid
        assert claims["ver"] == 2
        assert "alias" not in claims

    def test_build_claims_with_legacy_username(self):
        """Test building claims with legacy username converts to UUID."""
        legacy_username = "qazwsxppo"
        claims = build_claims(legacy_username)
        
        # Should be a valid UUID
        uuid.UUID(claims["sub"])
        assert claims["ver"] == 2
        assert "alias" not in claims

    def test_build_claims_with_alias(self):
        """Test building claims with alias for migration analytics."""
        user_uuid = str(uuid.uuid4())
        alias = "legacy_user"
        claims = build_claims(user_uuid, alias=alias)
        
        assert claims["sub"] == user_uuid
        assert claims["ver"] == 2
        assert claims["alias"] == alias

    def test_build_claims_deterministic_uuid(self):
        """Test that same legacy username produces same UUID."""
        legacy_username = "testuser"
        claims1 = build_claims(legacy_username)
        claims2 = build_claims(legacy_username)
        
        assert claims1["sub"] == claims2["sub"]
        assert claims1["ver"] == 2
        assert claims2["ver"] == 2

    def test_build_claims_always_uuid_sub(self):
        """CI guard: build_claims() must always set sub to a UUID."""
        test_cases = [
            "qazwsxppo",  # Legacy username
            "user123",    # Short username
            "a",          # Single character
            str(uuid.uuid4()),  # Already UUID
            "test-user_123",  # Username with special chars
        ]
        
        for user_id in test_cases:
            claims = build_claims(user_id)
            
            # sub must be a valid UUID
            try:
                uuid.UUID(claims["sub"])
            except ValueError:
                pytest.fail(f"build_claims() did not produce UUID sub for user_id: {user_id}")
            
            # sub must be 36 characters (standard UUID format)
            assert len(claims["sub"]) == 36, f"sub length is {len(claims['sub'])} for user_id: {user_id}"
            
            # ver must be 2 (UUID-only mode)
            assert claims["ver"] == 2, f"ver is {claims['ver']} for user_id: {user_id}"

    def test_build_claims_with_legacy_support(self):
        """Test legacy support mode for backward compatibility."""
        legacy_username = "qazwsxppo"
        claims = build_claims_with_legacy_support(legacy_username)
        
        # Should have both sub (UUID) and user_id (legacy)
        uuid.UUID(claims["sub"])  # sub should be UUID
        assert claims["user_id"] == legacy_username
        assert claims["ver"] == 1  # Legacy compatibility mode

    def test_build_claims_with_legacy_support_and_alias(self):
        """Test legacy support mode with alias."""
        legacy_username = "qazwsxppo"
        alias = "original_name"
        claims = build_claims_with_legacy_support(legacy_username, alias=alias)
        
        uuid.UUID(claims["sub"])  # sub should be UUID
        assert claims["user_id"] == legacy_username
        assert claims["alias"] == alias
        assert claims["ver"] == 1


class TestClaimsAnalysis:
    """Test JWT claims analysis functions."""

    def test_is_uuid_sub(self):
        """Test UUID sub detection."""
        # Version 2+ should be UUID-only
        assert is_uuid_sub({"ver": 2, "sub": str(uuid.uuid4())})
        assert is_uuid_sub({"ver": 3, "sub": str(uuid.uuid4())})
        
        # Version 1 should be legacy
        assert not is_uuid_sub({"ver": 1, "sub": "legacy_user"})
        
        # Default version should be legacy
        assert not is_uuid_sub({"sub": "legacy_user"})

    def test_get_user_uuid_from_claims(self):
        """Test extracting user UUID from claims."""
        user_uuid = str(uuid.uuid4())
        
        # UUID-only claims (version 2+)
        claims_v2 = {"ver": 2, "sub": user_uuid}
        assert get_user_uuid_from_claims(claims_v2) == user_uuid
        
        # Legacy claims with UUID sub
        claims_legacy_uuid = {"ver": 1, "sub": user_uuid, "user_id": "legacy"}
        assert get_user_uuid_from_claims(claims_legacy_uuid) == user_uuid
        
        # Legacy claims with legacy sub
        claims_legacy = {"ver": 1, "sub": "legacy_user", "user_id": "legacy_user"}
        result = get_user_uuid_from_claims(claims_legacy)
        uuid.UUID(result)  # Should be a valid UUID

    def test_get_legacy_alias_from_claims(self):
        """Test extracting legacy alias from claims."""
        # Explicit alias
        claims_with_alias = {"ver": 2, "sub": str(uuid.uuid4()), "alias": "legacy_user"}
        assert get_legacy_alias_from_claims(claims_with_alias) == "legacy_user"
        
        # Legacy claims with user_id as alias
        claims_legacy = {"ver": 1, "sub": str(uuid.uuid4()), "user_id": "legacy_user"}
        assert get_legacy_alias_from_claims(claims_legacy) == "legacy_user"
        
        # No alias
        claims_no_alias = {"ver": 2, "sub": str(uuid.uuid4())}
        assert get_legacy_alias_from_claims(claims_no_alias) is None


class TestLegacyResolutionTracking:
    """Test legacy sub resolution tracking."""

    def test_track_legacy_resolution(self):
        """Test tracking legacy sub resolutions."""
        initial_count = get_legacy_resolution_count()
        
        track_legacy_resolution("alias", "legacy_user", str(uuid.uuid4()))
        
        assert get_legacy_resolution_count() == initial_count + 1

    def test_track_legacy_resolution_multiple(self):
        """Test tracking multiple legacy sub resolutions."""
        initial_count = get_legacy_resolution_count()
        
        track_legacy_resolution("alias", "user1", str(uuid.uuid4()))
        track_legacy_resolution("username", "user2", str(uuid.uuid4()))
        
        assert get_legacy_resolution_count() == initial_count + 2


class TestIntegration:
    """Integration tests for JWT claims building."""

    def test_make_access_integration(self):
        """Test integration with make_access function."""
        from app.tokens import make_access
        
        # Test with UUID-only mode (default)
        user_uuid = str(uuid.uuid4())
        token = make_access({"user_id": user_uuid})
        
        # Decode and verify
        import jwt
        from app.security.jwt_config import get_jwt_config
        
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        assert decoded["sub"] == user_uuid
        assert decoded["ver"] == 2

    def test_make_access_with_legacy_username(self):
        """Test make_access with legacy username."""
        from app.tokens import make_access
        
        legacy_username = "qazwsxppo"
        token = make_access({"user_id": legacy_username})
        
        # Decode and verify
        import jwt
        from app.security.jwt_config import get_jwt_config
        
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        # sub should be UUID, not legacy username
        uuid.UUID(decoded["sub"])
        assert decoded["sub"] != legacy_username
        assert decoded["ver"] == 2

    def test_make_access_with_alias(self):
        """Test make_access with alias for migration analytics."""
        from app.tokens import make_access
        
        user_uuid = str(uuid.uuid4())
        alias = "legacy_user"
        token = make_access({"user_id": user_uuid, "alias": alias})
        
        # Decode and verify
        import jwt
        from app.security.jwt_config import get_jwt_config
        
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        assert decoded["sub"] == user_uuid
        assert decoded["alias"] == alias
        assert decoded["ver"] == 2

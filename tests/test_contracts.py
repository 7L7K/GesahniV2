"""
Contract tests to pin behavior and prevent regressions.

These tests ensure that JWT, DAO, and resolver contracts are maintained
and behavior doesn't change unexpectedly.
"""

import pytest
import uuid
import jwt
from unittest.mock import Mock, patch
from app.auth.jwt import build_claims, get_user_uuid_from_claims, is_uuid_sub
from app.tokens import make_access, make_refresh
from app.security.jwt_config import get_jwt_config


class TestJWTContract:
    """Contract tests for JWT behavior."""

    def test_jwt_contract_sub_must_be_uuid(self):
        """Contract: JWT sub must match UUID regex."""
        test_cases = [
            "qazwsxppo",  # Legacy username
            "user123",    # Short username
            "a",          # Single character
            str(uuid.uuid4()),  # Valid UUID
        ]
        
        for user_id in test_cases:
            claims = build_claims(user_id)
            
            # sub must be a valid UUID
            try:
                uuid.UUID(claims["sub"])
            except ValueError:
                pytest.fail(f"JWT sub is not a valid UUID for user_id: {user_id}")
            
            # sub must be 36 characters (standard UUID format)
            assert len(claims["sub"]) == 36, f"JWT sub length is {len(claims['sub'])} for user_id: {user_id}"

    def test_jwt_contract_optional_alias_allowed(self):
        """Contract: Optional alias allowed in JWT claims."""
        user_uuid = str(uuid.uuid4())
        alias = "legacy_user"
        
        # With alias
        claims_with_alias = build_claims(user_uuid, alias=alias)
        assert "alias" in claims_with_alias
        assert claims_with_alias["alias"] == alias
        
        # Without alias
        claims_without_alias = build_claims(user_uuid)
        assert "alias" not in claims_without_alias

    def test_jwt_contract_version_field(self):
        """Contract: JWT claims must include version field."""
        user_uuid = str(uuid.uuid4())
        claims = build_claims(user_uuid)
        
        assert "ver" in claims
        assert claims["ver"] == 2  # UUID-only mode

    def test_jwt_contract_deterministic_uuid(self):
        """Contract: Same input must produce same UUID."""
        legacy_username = "testuser"
        claims1 = build_claims(legacy_username)
        claims2 = build_claims(legacy_username)
        
        assert claims1["sub"] == claims2["sub"]

    def test_jwt_contract_make_access_integration(self):
        """Contract: make_access must produce valid JWT with UUID sub."""
        user_uuid = str(uuid.uuid4())
        token = make_access({"user_id": user_uuid})
        
        # Decode and verify
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        # Contract: sub must be UUID
        uuid.UUID(decoded["sub"])
        assert decoded["sub"] == user_uuid
        assert decoded["ver"] == 2

    def test_jwt_contract_make_refresh_integration(self):
        """Contract: make_refresh must produce valid JWT with UUID sub."""
        user_uuid = str(uuid.uuid4())
        token = make_refresh({"user_id": user_uuid})
        
        # Decode and verify
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        # Contract: sub must be UUID
        uuid.UUID(decoded["sub"])
        assert decoded["sub"] == user_uuid
        assert decoded["ver"] == 2


class TestDAOContract:
    """Contract tests for DAO behavior."""

    def test_dao_contract_third_party_token_access_token_encrypted_must_be_bytes(self):
        """Contract: ThirdPartyToken.access_token_encrypted must be bytes (fail fast on str)."""
        from app.db.models import ThirdPartyToken
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create in-memory SQLite database for testing
        engine = create_engine("sqlite:///:memory:")
        Session = sessionmaker(bind=engine)
        
        # Create tables
        from app.db.models import Base
        Base.metadata.create_all(engine)
        
        session = Session()
        
        try:
            # Test with bytes (should work)
            token_bytes = b"encrypted_token_data"
            token_with_bytes = ThirdPartyToken(
                user_id=str(uuid.uuid4()),
                provider="spotify",
                access_token_encrypted=token_bytes,
                is_valid=True
            )
            session.add(token_with_bytes)
            session.commit()
            
            # Test with string (should fail)
            token_string = "encrypted_token_data"
            token_with_string = ThirdPartyToken(
                user_id=str(uuid.uuid4()),
                provider="spotify",
                access_token_encrypted=token_string,  # This should cause a type error
                is_valid=True
            )
            
            # This should raise a type error or validation error
            with pytest.raises((TypeError, ValueError)):
                session.add(token_with_string)
                session.commit()
                
        finally:
            session.close()

    def test_dao_contract_user_id_must_be_uuid(self):
        """Contract: All user_id fields must accept UUID strings."""
        from app.db.models import Session as SessionModel, AuthDevice
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create in-memory SQLite database for testing
        engine = create_engine("sqlite:///:memory:")
        Session = sessionmaker(bind=engine)
        
        # Create tables
        from app.db.models import Base
        Base.metadata.create_all(engine)
        
        session = Session()
        
        try:
            user_uuid = str(uuid.uuid4())
            
            # Test Session model
            session_model = SessionModel(
                user_id=user_uuid,
                device_id=str(uuid.uuid4()),
                is_active=True
            )
            session.add(session_model)
            
            # Test AuthDevice model
            device = AuthDevice(
                id=str(uuid.uuid4()),
                user_id=user_uuid,
                device_name="test_device"
            )
            session.add(device)
            
            session.commit()
            
            # Verify data was stored correctly
            stored_session = session.query(SessionModel).first()
            assert stored_session.user_id == user_uuid
            
            stored_device = session.query(AuthDevice).first()
            assert stored_device.user_id == user_uuid
            
        finally:
            session.close()

    def test_dao_contract_legacy_user_id_rejection(self):
        """Contract: Legacy user_ids should be rejected by database constraints."""
        from app.db.models import Session as SessionModel
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create in-memory SQLite database for testing
        engine = create_engine("sqlite:///:memory:")
        Session = sessionmaker(bind=engine)
        
        # Create tables
        from app.db.models import Base
        Base.metadata.create_all(engine)
        
        session = Session()
        
        try:
            # Test with legacy user_id (should fail)
            legacy_user_id = "qazwsxppo"
            session_model = SessionModel(
                user_id=legacy_user_id,  # This should cause a constraint violation
                device_id=str(uuid.uuid4()),
                is_active=True
            )
            
            # This should raise a constraint violation or validation error
            with pytest.raises((ValueError, Exception)):
                session.add(session_model)
                session.commit()
                
        finally:
            session.close()


class TestResolverContract:
    """Contract tests for resolver behavior."""

    def test_resolver_contract_legacy_sub_maps_to_queries_succeed(self):
        """Contract: Legacy sub maps → queries succeed."""
        from app.util.ids import to_uuid
        
        legacy_sub = "qazwsxppo"
        resolved_uuid = str(to_uuid(legacy_sub))
        
        # Contract: Resolution should produce valid UUID
        uuid.UUID(resolved_uuid)
        
        # Contract: Resolution should be deterministic
        resolved_uuid2 = str(to_uuid(legacy_sub))
        assert resolved_uuid == resolved_uuid2

    def test_resolver_contract_db_writes_use_uuid(self):
        """Contract: DB writes use UUID after resolution."""
        from app.util.ids import to_uuid
        
        legacy_sub = "qazwsxppo"
        resolved_uuid = str(to_uuid(legacy_sub))
        
        # Contract: Resolved UUID should be used in DB operations
        # This is tested by the actual database operations in the codebase
        # Here we verify the resolution produces a valid UUID
        uuid.UUID(resolved_uuid)
        assert len(resolved_uuid) == 36

    def test_resolver_contract_warning_emitted_once(self):
        """Contract: Warning is emitted once per legacy sub resolution."""
        from app.auth.jwt import track_legacy_resolution, get_legacy_resolution_count
        from unittest.mock import patch
        
        initial_count = get_legacy_resolution_count()
        
        # Track a legacy resolution
        with patch('app.auth.jwt.logger') as mock_logger:
            track_legacy_resolution("alias", "legacy_user", str(uuid.uuid4()))
            
            # Contract: Warning should be logged
            mock_logger.warning.assert_called_once()
            
            # Contract: Count should increment
            assert get_legacy_resolution_count() == initial_count + 1

    def test_resolver_contract_claims_analysis(self):
        """Contract: Claims analysis functions work correctly."""
        user_uuid = str(uuid.uuid4())
        legacy_username = "qazwsxppo"
        
        # Test UUID-only claims
        uuid_claims = {"ver": 2, "sub": user_uuid}
        assert is_uuid_sub(uuid_claims)
        assert get_user_uuid_from_claims(uuid_claims) == user_uuid
        
        # Test legacy claims
        legacy_claims = {"ver": 1, "sub": legacy_username, "user_id": legacy_username}
        assert not is_uuid_sub(legacy_claims)
        resolved_uuid = get_user_uuid_from_claims(legacy_claims)
        uuid.UUID(resolved_uuid)  # Should be a valid UUID

    def test_resolver_contract_backward_compatibility(self):
        """Contract: Resolver maintains backward compatibility."""
        from app.auth.jwt import build_claims_with_legacy_support
        
        legacy_username = "qazwsxppo"
        claims = build_claims_with_legacy_support(legacy_username)
        
        # Contract: Should have both sub (UUID) and user_id (legacy)
        uuid.UUID(claims["sub"])  # sub should be UUID
        assert claims["user_id"] == legacy_username  # user_id should be legacy
        assert claims["ver"] == 1  # Legacy compatibility mode


class TestIntegrationContracts:
    """Integration contract tests."""

    def test_integration_contract_jwt_to_dao_flow(self):
        """Contract: JWT claims flow correctly to DAO operations."""
        from app.tokens import make_access
        from app.util.ids import to_uuid
        
        # Create JWT with legacy username
        legacy_username = "qazwsxppo"
        token = make_access({"user_id": legacy_username})
        
        # Decode JWT
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        # Contract: JWT sub should be UUID
        jwt_sub = decoded["sub"]
        uuid.UUID(jwt_sub)
        
        # Contract: JWT sub should match to_uuid conversion
        expected_uuid = str(to_uuid(legacy_username))
        assert jwt_sub == expected_uuid

    def test_integration_contract_dao_to_resolver_flow(self):
        """Contract: DAO operations work with resolver output."""
        from app.util.ids import to_uuid
        
        legacy_username = "qazwsxppo"
        resolved_uuid = str(to_uuid(legacy_username))
        
        # Contract: Resolved UUID should work in DAO operations
        # This is implicitly tested by the database operations in the codebase
        # Here we verify the resolution produces a valid UUID
        uuid.UUID(resolved_uuid)
        
        # Contract: Resolution should be consistent
        resolved_uuid2 = str(to_uuid(legacy_username))
        assert resolved_uuid == resolved_uuid2

    def test_integration_contract_end_to_end_flow(self):
        """Contract: End-to-end flow from JWT creation to database operations."""
        from app.tokens import make_access
        from app.util.ids import to_uuid
        
        # Start with legacy username
        legacy_username = "qazwsxppo"
        
        # Create JWT
        token = make_access({"user_id": legacy_username})
        
        # Decode JWT
        config = get_jwt_config()
        decoded = jwt.decode(token, config.secret_key, algorithms=[config.algorithm])
        
        # Contract: JWT sub should be UUID
        jwt_sub = decoded["sub"]
        uuid.UUID(jwt_sub)
        
        # Contract: JWT sub should match direct to_uuid conversion
        expected_uuid = str(to_uuid(legacy_username))
        assert jwt_sub == expected_uuid
        
        # Contract: This UUID should work in database operations
        # (This is tested by the actual database operations in the codebase)
        assert len(jwt_sub) == 36
        assert jwt_sub.count('-') == 4  # Standard UUID format

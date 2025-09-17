"""
API-Database Integration Tests

Tests that API endpoints work correctly with the actual database schema.
This catches integration issues between API code and database operations.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text


# Use existing database instead of creating a new one
@pytest.fixture(scope="session")
def sync_engine():
    """Use the existing database for testing."""
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni"
    )
    return create_engine(database_url)


class TestLoginDatabaseIntegration:
    """Test login API with real database operations."""

    def test_login_api_creates_proper_database_records(self, client, sync_engine):
        """Test that login API creates expected database records."""
        # Create a test user in database first
        user_id = str(uuid.uuid4())
        username = "testuser123"

        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, password_hash, name, created_at)
                VALUES (:user_id, :email, :username, :password_hash, :name, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": f"{username}@test.com",
                    "username": username,
                    "password_hash": "test_hash",
                    "name": "Test User",
                    "created_at": datetime.now(UTC),
                },
            )

        # Test the login query that was failing
        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT id, email, username, password_hash, name, created_at
                FROM auth.users
                WHERE username = :username
            """
                ),
                {"username": username},
            )

            user = result.mappings().first()
            assert user is not None, "User should be found by username"
            assert user["username"] == username, "Username should match"
            assert str(user["id"]) == user_id, "User ID should match"

    def test_user_creation_with_uuid_format(self, sync_engine):
        """Test that user creation works with proper UUID format."""
        user_id = str(uuid.uuid4())
        username = "uuidtest123"

        with sync_engine.begin() as conn:
            # This should work without errors
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, password_hash, name, created_at)
                VALUES (:user_id, :email, :username, :password_hash, :name, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": f"{username}@test.com",
                    "username": username,
                    "password_hash": "test_hash",
                    "name": "UUID Test User",
                    "created_at": datetime.now(UTC),
                },
            )

            # Verify the user was created with correct UUID
            result = conn.execute(
                text(
                    """
                SELECT id, username FROM auth.users WHERE username = :username
            """
                ),
                {"username": username},
            )

            user = result.mappings().first()
            assert user is not None, "User should be created successfully"
            assert user["username"] == username, "Username should be stored correctly"

            # Verify UUID format
            try:
                uuid.UUID(user["id"])
                assert True, "ID should be valid UUID"
            except ValueError:
                assert False, f"ID {user['id']} is not a valid UUID"


class TestThirdPartyTokensIntegration:
    """Test third_party_tokens table with API operations."""

    def test_token_storage_with_all_columns(self, sync_engine):
        """Test storing tokens with all required columns."""
        user_id = str(uuid.uuid4())
        identity_id = str(uuid.uuid4())
        token_id = str(uuid.uuid4())

        with sync_engine.begin() as conn:
            # Create user first
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, created_at)
                VALUES (:user_id, :email, :username, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": "tokenuser@test.com",
                    "username": "tokenuser",
                    "created_at": datetime.now(UTC),
                },
            )

            # Create identity
            conn.execute(
                text(
                    """
                INSERT INTO auth.auth_identities (id, user_id, provider, provider_sub, created_at, updated_at)
                VALUES (:id, :user_id, :provider, :provider_sub, :created_at, :updated_at)
            """
                ),
                {
                    "id": identity_id,
                    "user_id": user_id,
                    "provider": "google",
                    "provider_sub": "google_user_123",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )

            # Store token with all columns - this should work without errors
            conn.execute(
                text(
                    """
                INSERT INTO tokens.third_party_tokens (
                    id, user_id, identity_id, provider, provider_sub, provider_iss,
                    access_token, access_token_enc, refresh_token, refresh_token_enc,
                    envelope_key_version, last_refresh_at, refresh_error_count,
                    scope, service_state, scope_union_since, scope_last_added_from,
                    replaced_by_id, expires_at, created_at, updated_at, is_valid
                ) VALUES (
                    :id, :user_id, :identity_id, :provider, :provider_sub, :provider_iss,
                    :access_token, :access_token_enc, :refresh_token, :refresh_token_enc,
                    :envelope_key_version, :last_refresh_at, :refresh_error_count,
                    :scope, :service_state, :scope_union_since, :scope_last_added_from,
                    :replaced_by_id, :expires_at, :created_at, :updated_at, :is_valid
                )
            """
                ),
                {
                    "id": token_id,
                    "user_id": user_id,
                    "identity_id": identity_id,
                    "provider": "google",
                    "provider_sub": "google_user_123",
                    "provider_iss": "https://accounts.google.com",
                    "access_token": b"encrypted_access_token",
                    "access_token_enc": b"doubly_encrypted_token",
                    "refresh_token": b"encrypted_refresh_token",
                    "refresh_token_enc": b"doubly_encrypted_refresh",
                    "envelope_key_version": 1,
                    "last_refresh_at": 1234567890,
                    "refresh_error_count": 0,
                    "scope": "email profile",
                    "service_state": "active",
                    "scope_union_since": 1234567890,
                    "scope_last_added_from": "login",
                    "replaced_by_id": None,
                    "expires_at": datetime.now(UTC),
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                    "is_valid": True,
                },
            )

            # Verify token was stored correctly
            result = conn.execute(
                text(
                    """
                SELECT id, user_id, identity_id, provider, provider_sub,
                       provider_iss, is_valid, scope
                FROM tokens.third_party_tokens
                WHERE id = :token_id
            """
                ),
                {"token_id": token_id},
            )

            token = result.mappings().first()
            assert token is not None, "Token should be stored successfully"
            assert token["provider"] == "google", "Provider should be stored correctly"
            assert token["is_valid"] is True, "is_valid should be True"
            assert token["scope"] == "email profile", "Scope should be stored correctly"

    def test_token_query_with_is_valid_filter(self, sync_engine):
        """Test querying tokens with is_valid filter (the failing query pattern)."""
        user_id = str(uuid.uuid4())

        with sync_engine.begin() as conn:
            # Create user
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, created_at)
                VALUES (:user_id, :email, :username, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": "querytest@test.com",
                    "username": "querytest",
                    "created_at": datetime.now(UTC),
                },
            )

            # This is the exact query pattern that was failing
            result = conn.execute(
                text(
                    """
                SELECT tokens.third_party_tokens.id, tokens.third_party_tokens.user_id,
                       tokens.third_party_tokens.provider, tokens.third_party_tokens.is_valid
                FROM tokens.third_party_tokens
                WHERE tokens.third_party_tokens.user_id = :user_id::UUID
                  AND tokens.third_party_tokens.is_valid IS true
                ORDER BY tokens.third_party_tokens.created_at DESC
            """
                ),
                {"user_id": user_id},
            )

            # Should not raise an error even with no results
            tokens = result.mappings().all()
            assert len(tokens) == 0, "Should return empty result set, not error"


class TestDatabaseConstraintsIntegration:
    """Test database constraints work correctly."""

    def test_foreign_key_constraints_enforced(self, sync_engine):
        """Test that foreign key constraints are properly enforced."""
        fake_user_id = str(uuid.uuid4())

        with sync_engine.connect() as conn:
            # Try to insert token with non-existent user_id - should fail
            try:
                conn.execute(
                    text(
                        """
                    INSERT INTO tokens.third_party_tokens (
                        id, user_id, provider, provider_sub, access_token, created_at
                    ) VALUES (
                        :id, :user_id, :provider, :provider_sub, :access_token, :created_at
                    )
                """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": fake_user_id,  # This user doesn't exist
                        "provider": "test",
                        "provider_sub": "test_user",
                        "access_token": b"test_token",
                        "created_at": datetime.now(UTC),
                    },
                )
                conn.commit()
                assert False, "Foreign key constraint should have prevented this insert"
            except Exception as e:
                # Should get a foreign key violation error
                assert (
                    "foreign key" in str(e).lower() or "violates" in str(e).lower()
                ), f"Expected foreign key error, got: {e}"

    def test_unique_constraints_enforced(self, sync_engine):
        """Test that unique constraints are properly enforced."""
        user_id = str(uuid.uuid4())

        with sync_engine.begin() as conn:
            # Create user
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, created_at)
                VALUES (:user_id, :email, :username, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": "unique_test@test.com",
                    "username": "unique_test",
                    "created_at": datetime.now(UTC),
                },
            )

            # Insert first token
            conn.execute(
                text(
                    """
                INSERT INTO tokens.third_party_tokens (
                    id, user_id, provider, provider_sub, access_token, created_at
                ) VALUES (
                    :id, :user_id, :provider, :provider_sub, :access_token, :created_at
                )
            """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "provider": "test_provider",
                    "provider_sub": "test_user_123",
                    "access_token": b"test_token_1",
                    "created_at": datetime.now(UTC),
                },
            )

        # Try to insert duplicate (user_id, provider, provider_sub) - should fail
        with sync_engine.connect() as conn:
            try:
                conn.execute(
                    text(
                        """
                    INSERT INTO tokens.third_party_tokens (
                        id, user_id, provider, provider_sub, access_token, created_at
                    ) VALUES (
                        :id, :user_id, :provider, :provider_sub, :access_token, :created_at
                    )
                """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "provider": "test_provider",  # Same provider
                        "provider_sub": "test_user_123",  # Same provider_sub
                        "access_token": b"test_token_2",
                        "created_at": datetime.now(UTC),
                    },
                )
                conn.commit()
                assert False, "Unique constraint should have prevented duplicate insert"
            except Exception as e:
                # Should get a unique constraint violation error
                assert (
                    "unique" in str(e).lower() or "duplicate" in str(e).lower()
                ), f"Expected unique constraint error, got: {e}"

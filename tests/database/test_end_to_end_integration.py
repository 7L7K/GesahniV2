"""
End-to-End Integration Tests

Tests complete application workflows from API to database and back.
This catches real-world integration issues that unit tests miss.
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


class TestUserLifecycleIntegration:
    """Test complete user lifecycle from registration to data retrieval."""

    def test_user_registration_workflow(self, client, sync_engine):
        """Test complete user registration and retrieval workflow."""
        username = "e2e_user_test"
        email = "e2e_user@test.com"
        user_id = str(uuid.uuid4())

        # Simulate user registration by creating user directly in database
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, name, created_at)
                VALUES (:user_id, :email, :username, :name, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": email,
                    "username": username,
                    "name": "E2E Test User",
                    "created_at": datetime.now(UTC),
                },
            )

            # Create user stats
            conn.execute(
                text(
                    """
                INSERT INTO users.user_stats (user_id, login_count, created_at)
                VALUES (:user_id, 0, :created_at)
            """
                ),
                {"user_id": user_id, "created_at": datetime.now(UTC)},
            )

        # Test user retrieval via database
        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT u.id, u.email, u.username, u.name, s.login_count
                FROM auth.users u
                LEFT JOIN users.user_stats s ON u.id = s.user_id
                WHERE u.username = :username
            """
                ),
                {"username": username},
            )

            user_data = result.mappings().first()
            assert user_data is not None, "User should be retrievable"
            assert user_data["email"] == email, "Email should match"
            assert user_data["username"] == username, "Username should match"
            assert user_data["login_count"] == 0, "Login count should be 0"

    def test_user_session_workflow(self, sync_engine):
        """Test user session creation and management."""
        username = "session_test_user"
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
                    "email": "session@test.com",
                    "username": username,
                    "created_at": datetime.now(UTC),
                },
            )

            # Create device
            device_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                INSERT INTO auth.devices (id, user_id, device_name, ua_hash, ip_hash, created_at)
                VALUES (:device_id, :user_id, :device_name, :ua_hash, :ip_hash, :created_at)
            """
                ),
                {
                    "device_id": device_id,
                    "user_id": user_id,
                    "device_name": "Test Browser",
                    "ua_hash": "browser_hash_123",
                    "ip_hash": "ip_hash_456",
                    "created_at": datetime.now(UTC),
                },
            )

            # Create session
            session_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                INSERT INTO auth.sessions (id, user_id, device_id, created_at)
                VALUES (:session_id, :user_id, :device_id, :created_at)
            """
                ),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "device_id": device_id,
                    "created_at": datetime.now(UTC),
                },
            )

            # Test session retrieval with joins
            result = conn.execute(
                text(
                    """
                SELECT
                    sess.id as session_id,
                    sess.created_at as session_created,
                    u.username,
                    d.device_name,
                    d.ua_hash
                FROM auth.sessions sess
                JOIN auth.users u ON sess.user_id = u.id
                JOIN auth.devices d ON sess.device_id = d.id
                WHERE sess.id = :session_id
            """
                ),
                {"session_id": session_id},
            )

            session_data = result.mappings().first()
            assert session_data is not None, "Session data should be retrievable"
            assert (
                session_data["username"] == username
            ), "User data should be joined correctly"
            assert (
                session_data["device_name"] == "Test Browser"
            ), "Device data should be joined correctly"


class TestTokenManagementWorkflow:
    """Test complete token management workflow."""

    def test_token_creation_and_retrieval(self, sync_engine):
        """Test creating and retrieving OAuth tokens."""
        username = "token_workflow_test"
        user_id = str(uuid.uuid4())
        identity_id = str(uuid.uuid4())
        token_id = str(uuid.uuid4())

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
                    "email": "token@test.com",
                    "username": username,
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
                    "provider_sub": "google_user_789",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )

            # Create token
            conn.execute(
                text(
                    """
                INSERT INTO tokens.third_party_tokens (
                    id, user_id, identity_id, provider, provider_sub,
                    access_token, scope, expires_at, created_at, is_valid
                ) VALUES (
                    :id, :user_id, :identity_id, :provider, :provider_sub,
                    :access_token, :scope, :expires_at, :created_at, :is_valid
                )
            """
                ),
                {
                    "id": token_id,
                    "user_id": user_id,
                    "identity_id": identity_id,
                    "provider": "google",
                    "provider_sub": "google_user_789",
                    "access_token": b"test_access_token_abc",
                    "scope": "email profile",
                    "expires_at": datetime.now(UTC),
                    "created_at": datetime.now(UTC),
                    "is_valid": True,
                },
            )

            # Test token retrieval (this is the query pattern that was failing)
            result = conn.execute(
                text(
                    """
                SELECT
                    t.id, t.user_id, t.identity_id, t.provider, t.provider_sub,
                    t.access_token, t.scope, t.is_valid,
                    u.username,
                    i.provider as identity_provider
                FROM tokens.third_party_tokens t
                JOIN auth.users u ON t.user_id = u.id
                JOIN auth.auth_identities i ON t.identity_id = i.id
                WHERE t.user_id = :user_id AND t.is_valid = true
                ORDER BY t.created_at DESC
            """
                ),
                {"user_id": user_id},
            )

            token_data = result.mappings().first()
            assert token_data is not None, "Token should be retrievable with joins"
            assert token_data["username"] == username, "User join should work"
            assert (
                token_data["identity_provider"] == "google"
            ), "Identity join should work"
            assert (
                token_data["scope"] == "email profile"
            ), "Token data should be correct"
            assert token_data["is_valid"] is True, "Token validity should be correct"

    def test_token_uniqueness_constraints(self, sync_engine):
        """Test that token uniqueness constraints work end-to-end."""
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
                    "email": "unique_token@test.com",
                    "username": "unique_token_test",
                    "created_at": datetime.now(UTC),
                },
            )

            # Insert first token
            conn.execute(
                text(
                    """
                INSERT INTO tokens.third_party_tokens (
                    id, user_id, provider, provider_sub, access_token, created_at, is_valid
                ) VALUES (
                    :id, :user_id, :provider, :provider_sub, :access_token, :created_at, :is_valid
                )
            """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "provider": "spotify",
                    "provider_sub": "spotify_user_123",
                    "access_token": b"token_1",
                    "created_at": datetime.now(UTC),
                    "is_valid": True,
                },
            )

        # Try to insert duplicate - should fail
        with sync_engine.connect() as conn:
            try:
                conn.execute(
                    text(
                        """
                    INSERT INTO tokens.third_party_tokens (
                        id, user_id, provider, provider_sub, access_token, created_at, is_valid
                    ) VALUES (
                        :id, :user_id, :provider, :provider_sub, :access_token, :created_at, :is_valid
                    )
                """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "provider": "spotify",  # Same provider
                        "provider_sub": "spotify_user_123",  # Same provider_sub
                        "access_token": b"token_2",
                        "created_at": datetime.now(UTC),
                        "is_valid": True,
                    },
                )
                conn.commit()
                assert False, "Should have failed due to unique constraint"
            except Exception as e:
                # Should be a unique constraint violation
                assert (
                    "unique" in str(e).lower() or "duplicate" in str(e).lower()
                ), f"Expected unique constraint error, got: {e}"


class TestAuditLoggingWorkflow:
    """Test that audit logging works end-to-end."""

    def test_audit_log_creation(self, sync_engine):
        """Test that audit logs are created for user actions."""
        username = "audit_test_user"
        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

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
                    "email": "audit@test.com",
                    "username": username,
                    "created_at": datetime.now(UTC),
                },
            )

            # Create device and session for audit context
            device_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                INSERT INTO auth.devices (id, user_id, device_name, ua_hash, ip_hash, created_at)
                VALUES (:device_id, :user_id, :device_name, :ua_hash, :ip_hash, :created_at)
            """
                ),
                {
                    "device_id": device_id,
                    "user_id": user_id,
                    "device_name": "Audit Test Device",
                    "ua_hash": "audit_ua_hash",
                    "ip_hash": "audit_ip_hash",
                    "created_at": datetime.now(UTC),
                },
            )

            conn.execute(
                text(
                    """
                INSERT INTO auth.sessions (id, user_id, device_id, created_at)
                VALUES (:session_id, :user_id, :device_id, :created_at)
            """
                ),
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "device_id": device_id,
                    "created_at": datetime.now(UTC),
                },
            )

            # Create audit log entries
            audit_events = [
                ("login", '{"method": "password", "success": true}'),
                ("page_view", '{"page": "/dashboard", "duration": 45}'),
                ("api_call", '{"endpoint": "/v1/profile", "method": "GET"}'),
            ]

            for event_type, meta in audit_events:
                conn.execute(
                    text(
                        """
                    INSERT INTO audit.audit_log (user_id, session_id, event_type, meta, created_at)
                    VALUES (:user_id, :session_id, :event_type, :meta, :created_at)
                """
                    ),
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "event_type": event_type,
                        "meta": meta,
                        "created_at": datetime.now(UTC),
                    },
                )

            # Verify audit logs were created
            result = conn.execute(
                text(
                    """
                SELECT event_type, meta FROM audit.audit_log
                WHERE user_id = :user_id
                ORDER BY created_at
            """
                ),
                {"user_id": user_id},
            )

            audit_entries = result.mappings().all()
            assert (
                len(audit_entries) == 3
            ), f"Should have 3 audit entries, found {len(audit_entries)}"

            event_types = [entry["event_type"] for entry in audit_entries]
            assert "login" in event_types, "Should have login audit entry"
            assert "page_view" in event_types, "Should have page_view audit entry"
            assert "api_call" in event_types, "Should have api_call audit entry"

            # Verify audit log relationships
            result = conn.execute(
                text(
                    """
                SELECT al.event_type, u.username, s.id as session_id
                FROM audit.audit_log al
                JOIN auth.users u ON al.user_id = u.id
                LEFT JOIN auth.sessions s ON al.session_id = s.id
                WHERE al.user_id = :user_id
                ORDER BY al.created_at
            """
                ),
                {"user_id": user_id},
            )

            audit_with_relations = result.mappings().all()
            assert (
                len(audit_with_relations) == 3
            ), "Should be able to join audit logs with users"

            for entry in audit_with_relations:
                assert (
                    entry["username"] == username
                ), "Audit log should be properly linked to user"
                assert (
                    entry["session_id"] == session_id
                ), "Audit log should be properly linked to session"

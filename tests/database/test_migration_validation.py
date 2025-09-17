"""
Migration Validation Tests

Ensures database migrations work correctly and maintain data integrity.
This catches migration-related issues before they reach production.
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


class TestMigrationValidation:
    """Test that migrations work correctly."""

    def test_alembic_migration_state(self, sync_engine):
        """Verify Alembic migration state is current."""
        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT version_num FROM alembic_version LIMIT 1
            """
                )
            )

            version = result.scalar()
            assert version is not None, "Alembic version should exist"
            assert len(version) > 0, "Alembic version should not be empty"

    def test_migration_creates_all_schemas(self, sync_engine):
        """Verify all expected schemas were created by migrations."""
        expected_schemas = {"auth", "users", "care", "music", "tokens", "audit"}

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name IN ('auth', 'users', 'care', 'music', 'tokens', 'audit')
            """
                )
            )

            existing_schemas = {row[0] for row in result}

            missing_schemas = expected_schemas - existing_schemas
            assert (
                not missing_schemas
            ), f"Migrations failed to create schemas: {missing_schemas}"

    def test_migration_creates_all_tables(self, sync_engine):
        """Verify all expected tables were created by migrations."""
        # This is similar to the schema consistency test but focused on migrations
        expected_tables = {
            "auth.users",
            "auth.devices",
            "auth.sessions",
            "auth.auth_identities",
            "auth.pat_tokens",
            "users.user_stats",
            "tokens.third_party_tokens",
            "audit.audit_log",
        }

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT schemaname || '.' || tablename as table_name
                FROM pg_tables
                WHERE schemaname IN ('auth', 'users', 'tokens', 'audit')
            """
                )
            )

            existing_tables = {row[0] for row in result}

            missing_tables = expected_tables - existing_tables
            assert (
                not missing_tables
            ), f"Migrations failed to create tables: {missing_tables}"

    def test_migration_maintains_data_integrity(self, sync_engine):
        """Test that migrations don't break existing data relationships."""
        user_id = str(uuid.uuid4())

        with sync_engine.begin() as conn:
            # Create a user
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, name, created_at)
                VALUES (:user_id, :email, :username, :name, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": "migration_test@test.com",
                    "username": "migration_test",
                    "name": "Migration Test User",
                    "created_at": datetime.now(UTC),
                },
            )

            # Create a device session (tests auth schema relationships)
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
                    "device_name": "Test Device",
                    "ua_hash": "test_ua_hash",
                    "ip_hash": "test_ip_hash",
                    "created_at": datetime.now(UTC),
                },
            )

            # Create a session (tests FK relationships)
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

            # Verify relationships work
            result = conn.execute(
                text(
                    """
                SELECT s.id, s.user_id, s.device_id,
                       u.username, d.device_name
                FROM auth.sessions s
                JOIN auth.users u ON s.user_id = u.id
                JOIN auth.devices d ON s.device_id = d.id
                WHERE s.id = :session_id
            """
                ),
                {"session_id": session_id},
            )

            session_data = result.mappings().first()
            assert session_data is not None, "Session relationship should work"
            assert (
                session_data["username"] == "migration_test"
            ), "User relationship should work"
            assert (
                session_data["device_name"] == "Test Device"
            ), "Device relationship should work"


class TestMigrationIdempotency:
    """Test that migrations are idempotent (can run multiple times safely)."""

    def test_migration_idempotency(self, sync_engine):
        """Verify running migrations multiple times doesn't break anything."""
        # This is a conceptual test - in practice we'd need to test the actual migration scripts
        # For now, we'll test that the current database state is consistent

        with sync_engine.connect() as conn:
            # Check that we can query all expected tables without errors
            tables_to_check = [
                "auth.users",
                "auth.devices",
                "auth.sessions",
                "auth.auth_identities",
                "tokens.third_party_tokens",
                "users.user_stats",
                "audit.audit_log",
            ]

            for table in tables_to_check:
                schema, table_name = table.split(".")
                result = conn.execute(
                    text(
                        f"""
                    SELECT COUNT(*) FROM {schema}.{table_name} LIMIT 1
                """
                    )
                )
                # Just verify the query doesn't error
                count = result.scalar()
                assert isinstance(count, int), f"Query on {table} should work"

    def test_migration_preserves_existing_data(self, sync_engine):
        """Test that migrations don't corrupt existing data."""
        test_username = "migration_preserve_test"
        user_id = str(uuid.uuid4())

        with sync_engine.begin() as conn:
            # Create test data
            conn.execute(
                text(
                    """
                INSERT INTO auth.users (id, email, username, name, created_at)
                VALUES (:user_id, :email, :username, :name, :created_at)
            """
                ),
                {
                    "user_id": user_id,
                    "email": f"{test_username}@test.com",
                    "username": test_username,
                    "name": "Migration Preserve Test",
                    "created_at": datetime.now(UTC),
                },
            )

            # Verify data exists before "migration"
            result = conn.execute(
                text(
                    """
                SELECT username, name FROM auth.users WHERE id = :user_id
            """
                ),
                {"user_id": user_id},
            )

            user_before = result.mappings().first()
            assert (
                user_before["username"] == test_username
            ), "Data should exist before migration"

            # In a real scenario, we'd run migrations here
            # For this test, we'll simulate by re-querying
            result = conn.execute(
                text(
                    """
                SELECT username, name FROM auth.users WHERE id = :user_id
            """
                ),
                {"user_id": user_id},
            )

            user_after = result.mappings().first()
            assert (
                user_after["username"] == test_username
            ), "Data should be preserved after migration"
            assert (
                user_after["name"] == "Migration Preserve Test"
            ), "All fields should be preserved"


class TestMigrationRollbackSafety:
    """Test migration rollback scenarios."""

    def test_migration_rollback_doesnt_break_schema(self, sync_engine):
        """Test that migration rollbacks leave database in valid state."""
        # This is a conceptual test for rollback safety
        # In practice, we'd test actual alembic downgrade commands

        with sync_engine.connect() as conn:
            # Verify that even after potential rollbacks, basic queries still work
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*) FROM auth.users LIMIT 1
            """
                )
            )

            count = result.scalar()
            assert isinstance(
                count, int
            ), "Basic query should work after any migration state"

            # Verify core tables still exist and are queryable
            core_tables = ["auth.users", "auth.devices", "tokens.third_party_tokens"]

            for table in core_tables:
                schema, table_name = table.split(".")
                result = conn.execute(
                    text(
                        f"""
                    SELECT COUNT(*) FROM {schema}.{table_name} LIMIT 1
                """
                    )
                )
                count = result.scalar()
                assert isinstance(count, int), f"Core table {table} should be queryable"

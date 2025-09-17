"""
Schema Consistency Tests

Validates that test database setup matches production Alembic migrations.
This prevents "works in test, fails in production" issues.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# Use existing database instead of creating a new one
@pytest.fixture(scope="session")
def sync_engine():
    """Use the existing database for testing."""
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni"
    )
    return create_engine(database_url)


class TestSchemaConsistency:
    """Ensure test and production schemas match."""

    def test_production_schema_has_required_tables(self, sync_engine: Engine):
        """Verify all expected tables exist in production schema."""
        expected_tables = {
            # Auth schema
            "auth.users",
            "auth.devices",
            "auth.sessions",
            "auth.auth_identities",
            "auth.pat_tokens",
            # Users schema
            "users.user_stats",
            # Care schema
            "care.residents",
            "care.caregivers",
            "care.caregiver_resident",
            "care.devices",
            "care.alerts",
            "care.alert_events",
            "care.care_sessions",
            "care.contacts",
            "care.tv_config",
            # Music schema
            "music.music_devices",
            "music.music_tokens",
            "music.music_preferences",
            "music.music_sessions",
            "music.music_queue",
            "music.music_feedback",
            "music.music_states",
            # Tokens schema
            "tokens.third_party_tokens",
            # Audit schema
            "audit.audit_log",
        }

        with sync_engine.connect() as conn:
            # Get all existing tables
            result = conn.execute(
                text(
                    """
                SELECT schemaname || '.' || tablename as table_name
                FROM pg_tables
                WHERE schemaname IN ('auth', 'users', 'care', 'music', 'tokens', 'audit')
                ORDER BY schemaname, tablename
            """
                )
            )

            existing_tables = {row[0] for row in result}

            missing_tables = expected_tables - existing_tables
            assert not missing_tables, f"Missing tables: {missing_tables}"

            extra_tables = existing_tables - expected_tables
            assert not extra_tables, f"Unexpected tables: {extra_tables}"

    def test_auth_users_has_required_columns(self, sync_engine: Engine):
        """Verify auth.users table has all required columns."""
        required_columns = {
            "id",
            "email",
            "username",
            "password_hash",
            "name",
            "avatar_url",
            "created_at",
            "verified_at",
            "auth_providers",
        }

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'auth' AND table_name = 'users'
                ORDER BY column_name
            """
                )
            )

            existing_columns = {row[0] for row in result}

            missing_columns = required_columns - existing_columns
            assert not missing_columns, f"auth.users missing columns: {missing_columns}"

    def test_third_party_tokens_has_required_columns(self, sync_engine: Engine):
        """Verify tokens.third_party_tokens table has all required columns."""
        required_columns = {
            "id",
            "user_id",
            "identity_id",
            "provider",
            "provider_sub",
            "provider_iss",
            "access_token",
            "access_token_enc",
            "refresh_token",
            "refresh_token_enc",
            "envelope_key_version",
            "last_refresh_at",
            "refresh_error_count",
            "scope",
            "service_state",
            "scope_union_since",
            "scope_last_added_from",
            "replaced_by_id",
            "expires_at",
            "created_at",
            "updated_at",
            "is_valid",
        }

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'tokens' AND table_name = 'third_party_tokens'
                ORDER BY column_name
            """
                )
            )

            existing_columns = {row[0] for row in result}

            missing_columns = required_columns - existing_columns
            assert (
                not missing_columns
            ), f"tokens.third_party_tokens missing columns: {missing_columns}"

    def test_foreign_key_constraints_exist(self, sync_engine: Engine):
        """Verify important foreign key constraints exist."""
        expected_fks = {
            ("tokens.third_party_tokens", "user_id", "auth.users", "id"),
            ("tokens.third_party_tokens", "identity_id", "auth.auth_identities", "id"),
            ("auth.sessions", "user_id", "auth.users", "id"),
            ("auth.devices", "user_id", "auth.users", "id"),
            ("auth.auth_identities", "user_id", "auth.users", "id"),
        }

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT
                    tc.table_schema || '.' || tc.table_name as table_name,
                    kcu.column_name,
                    ccu.table_schema || '.' || ccu.table_name as referenced_table,
                    ccu.column_name as referenced_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema IN ('auth', 'tokens')
            """
                )
            )

            existing_fks = {(row[0], row[1], row[2], row[3]) for row in result}

            for expected_fk in expected_fks:
                assert expected_fk in existing_fks, f"Missing FK: {expected_fk}"

    def test_unique_constraints_exist(self, sync_engine: Engine):
        """Verify important unique constraints exist."""
        with sync_engine.connect() as conn:
            # Check auth.users email unique constraint
            result = conn.execute(
                text(
                    """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema = 'auth'
                  AND table_name = 'users'
                  AND constraint_type = 'UNIQUE'
            """
                )
            )

            constraints = {row[0] for row in result}
            assert any(
                "email" in c.lower() for c in constraints
            ), "auth.users missing email unique constraint"

            # Check tokens.third_party_tokens unique constraint
            result = conn.execute(
                text(
                    """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema = 'tokens'
                  AND table_name = 'third_party_tokens'
                  AND constraint_type = 'UNIQUE'
            """
                )
            )

            constraints = {row[0] for row in result}
            # Should have unique constraint on (user_id, provider, provider_sub)
            assert (
                len(constraints) > 0
            ), "tokens.third_party_tokens missing unique constraints"

    def test_indexes_exist(self, sync_engine: Engine):
        """Verify important indexes exist."""
        expected_indexes = {
            "tokens.idx_tokens_valid_expires_at",
            "tokens.idx_tokens_valid_provider_sub",
            "tokens.third_party_tokens_pkey",
        }

        with sync_engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                SELECT schemaname || '.' || indexname as index_name
                FROM pg_indexes
                WHERE schemaname = 'tokens'
            """
                )
            )

            existing_indexes = {row[0] for row in result}

            for expected_index in expected_indexes:
                assert (
                    expected_index in existing_indexes
                ), f"Missing index: {expected_index}"

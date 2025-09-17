#!/usr/bin/env python3
"""
Standalone database schema test

This test verifies that the database schema matches expectations
without relying on pytest fixtures that might conflict.
"""

import os

from sqlalchemy import create_engine, text


def test_database_schema():
    """Test that the database has the expected schema."""
    # Use existing database
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni"
    )
    engine = create_engine(database_url)

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

    with engine.connect() as conn:
        # Get all existing tables
        result = conn.execute(
            text(
                """
            SELECT schemaname || '.' || tablename as table_name
            FROM pg_tables
            WHERE schemaname IN ('auth', 'users', 'tokens', 'audit')
            ORDER BY schemaname, tablename
        """
            )
        )

        existing_tables = {row[0] for row in result}

        print(f"Expected tables: {len(expected_tables)}")
        print(f"Existing tables: {len(existing_tables)}")

        missing_tables = expected_tables - existing_tables
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False

        extra_tables = existing_tables - expected_tables
        if extra_tables:
            print(f"⚠️  Extra tables: {extra_tables}")

        # Test specific table structure
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

        user_columns = {row[0] for row in result}
        expected_user_columns = {
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

        missing_columns = expected_user_columns - user_columns
        if missing_columns:
            print(f"❌ Missing user columns: {missing_columns}")
            return False

        print("✅ Database schema test passed!")
        return True


if __name__ == "__main__":
    success = test_database_schema()
    exit(0 if success else 1)

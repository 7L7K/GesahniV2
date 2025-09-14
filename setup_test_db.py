#!/usr/bin/env python3
"""
Database setup script for tests.
Ensures all required tables exist for test execution.
"""

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def create_missing_tables():
    """Create missing tables that tests expect to exist."""

    # Get test database directory
    test_db_dir = os.getenv("GESAHNI_TEST_DB_DIR", "/tmp/gesahni_tests/main")

    # Ensure directory exists
    Path(test_db_dir).mkdir(parents=True, exist_ok=True)

    # Define the missing tables and their schemas
    tables_to_create = {
        "users": """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name TEXT,
                avatar_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                verified_at DATETIME,
                auth_providers TEXT
            );
        """,
        "auth_identities": """
            CREATE TABLE IF NOT EXISTS auth_identities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_iss TEXT,
                provider_sub TEXT,
                email_normalized TEXT,
                email_verified BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, provider_iss, provider_sub)
            );
        """,
        "third_party_tokens": """
            CREATE TABLE IF NOT EXISTS third_party_tokens (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                access_token BLOB,
                refresh_token BLOB,
                scope TEXT,
                expires_at DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, provider)
            );
        """,
        "user_stats": """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id TEXT PRIMARY KEY,
                login_count INTEGER DEFAULT 0,
                last_login DATETIME,
                request_count INTEGER DEFAULT 0
            );
        """,
    }

    # Main database files to check/update
    db_files = [
        "auth.db",
        "users.db",
        "third_party_tokens.db",
        f"{test_db_dir}/auth.db",
        f"{test_db_dir}/users.db",
        f"{test_db_dir}/third_party_tokens.db",
    ]

    for db_file in db_files:
        try:
            print(f"Setting up tables in {db_file}")
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()

            for table_name, create_sql in tables_to_create.items():
                cursor.execute(create_sql)
                print(f"  ✓ Created/ensured {table_name} table")

            conn.commit()
            conn.close()
            print(f"  ✓ Database {db_file} setup complete")

        except Exception as e:
            print(f"  ✗ Failed to setup {db_file}: {e}")
            continue


async def async_db_setup():
    """Async database setup for stores that need it."""
    try:
        # Try to import and setup the stores
        import app.auth_store as _auth_store
        import app.auth_store_tokens as _auth_tokens
        import app.care_store as _care_store
        import app.music.store as _music_store

        print("Setting up async database stores...")

        try:
            await _auth_store.ensure_tables()
            print("  ✓ Auth store tables ensured")
        except Exception as e:
            print(f"  ✗ Auth store setup failed: {e}")

        try:
            # Token DAO setup
            dao = _auth_tokens.TokenDAO(
                str(
                    getattr(
                        _auth_tokens.TokenDAO,
                        "DEFAULT_DB_PATH",
                        "third_party_tokens.db",
                    )
                )
            )
            await dao._ensure_table()
            print("  ✓ Token store tables ensured")
        except Exception as e:
            print(f"  ✗ Token store setup failed: {e}")

        try:
            await _care_store.ensure_tables()
            print("  ✓ Care store tables ensured")
        except Exception as e:
            print(f"  ✗ Care store setup failed: {e}")

        try:
            await _music_store._ensure_tables()
            print("  ✓ Music store tables ensured")
        except Exception as e:
            print(f"  ✗ Music store setup failed: {e}")

    except ImportError as e:
        print(f"Could not import database modules: {e}")
    except Exception as e:
        print(f"Async setup failed: {e}")


def main():
    """Main setup function."""
    print("🚀 Setting up test databases...")

    # Set test environment variables
    os.environ.setdefault("PYTEST_RUNNING", "1")
    os.environ.setdefault("TEST_MODE", "1")

    # Create missing tables synchronously
    create_missing_tables()

    # Run async setup
    try:
        asyncio.run(async_db_setup())
    except Exception as e:
        print(f"Async setup failed: {e}")

    print("✅ Database setup complete!")


if __name__ == "__main__":
    main()

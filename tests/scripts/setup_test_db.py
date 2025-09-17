#!/usr/bin/env python3
"""
Database setup script for tests.
Ensures all required tables exist for test execution.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from app.db.core import sync_engine


def create_missing_tables():
    """Create missing tables that tests expect to exist using PostgreSQL."""

    print("Setting up test database tables using PostgreSQL...")

    # Define the missing tables and their schemas for PostgreSQL
    tables_to_create = {
        "users": """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name TEXT,
                avatar_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP,
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
                email_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, provider_iss, provider_sub)
            );
        """,
        "third_party_tokens": """
            CREATE TABLE IF NOT EXISTS third_party_tokens (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                scope TEXT,
                expires_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, provider)
            );
        """,
        "user_stats": """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id TEXT PRIMARY KEY,
                login_count INTEGER DEFAULT 0,
                last_login TIMESTAMP,
                request_count INTEGER DEFAULT 0
            );
        """,
    }

    try:
        with sync_engine.connect() as conn:
            for table_name, create_sql in tables_to_create.items():
                conn.execute(text(create_sql))
                print(f"  ✓ Created/ensured {table_name} table")
            conn.commit()
        print("  ✓ PostgreSQL database setup complete")

    except Exception as e:
        print(f"  ✗ Failed to setup PostgreSQL database: {e}")
        raise


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
            # Token DAO setup - use PostgreSQL configuration
            dao = _auth_tokens.TokenDAO()
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

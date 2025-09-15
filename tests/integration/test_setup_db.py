#!/usr/bin/env python3
"""
Script to set up test database tables before running tests.
This ensures all required tables exist for test execution.
"""

import os
import sys
from pathlib import Path

# Add app to path to import database modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from app.db.core import sync_engine


def setup_test_db():
    """Create test database with all required tables using PostgreSQL."""

    print("Setting up test database tables using PostgreSQL...")

    # Use the configured PostgreSQL database
    try:
        with sync_engine.connect() as conn:
            # care_sessions table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS care_sessions (
                    id TEXT PRIMARY KEY,
                    resident_id TEXT,
                    title TEXT,
                    transcript_uri TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))
            print("✓ Created/ensured care_sessions table")

            # auth_users table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS auth_users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL
                )
            """))
            print("✓ Created/ensured auth_users table")

            # contacts table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    resident_id TEXT,
                    name TEXT,
                    phone TEXT,
                    priority INTEGER,
                    quiet_hours TEXT
                )
            """))
            print("✓ Created/ensured contacts table")

            # tv_config table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tv_config (
                    resident_id TEXT PRIMARY KEY,
                    ambient_rotation INTEGER,
                    rail TEXT,
                    quiet_hours TEXT,
                    default_vibe TEXT,
                    updated_at TIMESTAMP
                )
            """))
            print("✓ Created/ensured tv_config table")

            # music_tokens table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS music_tokens (
                    id SERIAL PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at INTEGER,
                    scope TEXT,
                    UNIQUE(provider, provider_user_id)
                )
            """))
            print("✓ Created/ensured music_tokens table")

            # third_party_tokens table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS third_party_tokens (
                    id SERIAL PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_sub TEXT NOT NULL,
                    access_token TEXT,
                    refresh_token TEXT,
                    expires_at INTEGER,
                    token_type TEXT,
                    scope TEXT,
                    UNIQUE(identity_id, provider)
                )
            """))
            print("✓ Created/ensured third_party_tokens table")

            # auth_identities table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS auth_identities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_iss TEXT,
                    provider_sub TEXT NOT NULL,
                    email_normalized TEXT,
                    email_verified INTEGER,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES auth_users(username)
                )
            """))
            print("✓ Created/ensured auth_identities table")

            # pat_tokens table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pat_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    scopes TEXT,
                    exp_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL,
                    revoked_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES auth_users(username)
                )
            """))
            print("✓ Created/ensured pat_tokens table")

            # notes table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notes (
                    text TEXT
                )
            """))
            print("✓ Created/ensured notes table")

            conn.commit()

        print("Test database setup complete using PostgreSQL")
        return "PostgreSQL database"

    except Exception as e:
        print(f"Database setup failed: {e}")
        raise


if __name__ == "__main__":
    setup_test_db()

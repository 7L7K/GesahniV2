#!/usr/bin/env python3
"""
Script to set up test database tables before running tests.
This ensures all required tables exist for test execution.
"""

import os
import sqlite3
import tempfile


def setup_test_db():
    """Create test database with all required tables."""

    # Get test DB path - check all possible env vars
    test_db_path = os.getenv("CARE_DB") or os.getenv("AUTH_DB") or os.getenv("MUSIC_DB")

    if not test_db_path:
        # Create a temp file if not set
        test_db_path = tempfile.mktemp(suffix=".db")
        print(f"No DB path env vars found, using temp file: {test_db_path}")
    else:
        print(f"Using DB path from env: {test_db_path}")

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(test_db_path), exist_ok=True)

    # Create all tables
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    # care_sessions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS care_sessions (
            id TEXT PRIMARY KEY,
            resident_id TEXT,
            title TEXT,
            transcript_uri TEXT,
            created_at REAL,
            updated_at REAL
        )
    """
    )

    # auth_users table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
    """
    )

    # contacts table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY,
            resident_id TEXT,
            name TEXT,
            phone TEXT,
            priority INTEGER,
            quiet_hours TEXT
        )
    """
    )

    # tv_config table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tv_config (
            resident_id TEXT PRIMARY KEY,
            ambient_rotation INTEGER,
            rail TEXT,
            quiet_hours TEXT,
            default_vibe TEXT,
            updated_at REAL
        )
    """
    )

    # music_tokens table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS music_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at INTEGER,
            scope TEXT,
            UNIQUE(provider, provider_user_id)
        )
    """
    )

    # third_party_tokens table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS third_party_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    """
    )

    # auth_identities table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_identities (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_iss TEXT,
            provider_sub TEXT NOT NULL,
            email_normalized TEXT,
            email_verified INTEGER,
            created_at REAL,
            updated_at REAL,
            FOREIGN KEY (user_id) REFERENCES auth_users(username)
        )
    """
    )

    # pat_tokens table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pat_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            scopes TEXT,
            exp_at REAL,
            created_at REAL NOT NULL,
            revoked_at REAL,
            FOREIGN KEY (user_id) REFERENCES auth_users(username)
        )
    """
    )

    # notes table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            text TEXT
        )
    """
    )

    conn.commit()
    conn.close()

    print(f"Test database setup complete at: {test_db_path}")
    return test_db_path


if __name__ == "__main__":
    setup_test_db()

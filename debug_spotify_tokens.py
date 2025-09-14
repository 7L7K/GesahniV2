#!/usr/bin/env python3
"""
Debug script to check Spotify tokens in the database.
"""

import os
import sqlite3


def check_spotify_tokens():
    """Check for Spotify tokens in the database."""

    print("🔍 Checking Spotify Tokens in Database")
    print("=" * 50)

    # Find the database file
    db_paths = [
        "third_party_tokens.db",
        "data/third_party_tokens.db",
        "app/third_party_tokens.db",
    ]

    db_file = None
    for path in db_paths:
        if os.path.exists(path):
            db_file = path
            break

    if not db_file:
        print("❌ No third_party_tokens.db found")
        return

    print(f"📁 Database: {db_file}")

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='third_party_tokens'"
        )
        table_exists = cursor.fetchone()

        if not table_exists:
            print("❌ third_party_tokens table doesn't exist")
            return

        print("✅ third_party_tokens table exists")

        # Get all Spotify tokens - check schema first
        cursor.execute("PRAGMA table_info(third_party_tokens)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        print(f"📊 Table columns: {column_names}")

        # Build query based on available columns
        select_columns = [
            "id",
            "user_id",
            "provider",
            "access_token",
            "refresh_token",
            "expires_at",
            "scope",
            "created_at",
            "updated_at",
        ]
        if "invalid" in column_names:
            select_columns.append("invalid")

        query = f"SELECT {', '.join(select_columns)} FROM third_party_tokens WHERE provider = 'spotify'"
        cursor.execute(query)
        rows = cursor.fetchall()

        print(f"📊 Found {len(rows)} Spotify tokens")

        for row in rows:
            # Unpack based on actual column count
            row_data = dict(zip(column_names, row, strict=False))

            print("\n🎵 Spotify Token Details:")
            print(f"  ID: {row_data.get('id')}")
            print(f"  User ID: {row_data.get('user_id')}")
            print(f"  Provider: {row_data.get('provider')}")
            print(
                f"  Access Token: {'✅ Present' if row_data.get('access_token') else '❌ Missing'} ({len(row_data.get('access_token') or '')} chars)"
            )
            print(
                f"  Refresh Token: {'✅ Present' if row_data.get('refresh_token') else '❌ Missing'} ({len(row_data.get('refresh_token') or '')} chars)"
            )
            print(f"  Expires At: {row_data.get('expires_at')}")
            print(f"  Scope: {row_data.get('scope')}")
            print(f"  Created At: {row_data.get('created_at')}")
            print(f"  Updated At: {row_data.get('updated_at')}")
            if "invalid" in row_data:
                print(f"  Invalid: {row_data.get('invalid')}")

        # Also check for any tokens at all
        cursor.execute("SELECT COUNT(*) FROM third_party_tokens")
        total_count = cursor.fetchone()[0]
        print(f"\n📊 Total tokens in database: {total_count}")

        # Check for all providers
        cursor.execute(
            "SELECT provider, COUNT(*) FROM third_party_tokens GROUP BY provider"
        )
        provider_counts = cursor.fetchall()

        print("\n📊 Tokens by provider:")
        for provider, count in provider_counts:
            print(f"  {provider}: {count}")

        conn.close()

    except Exception as e:
        print(f"❌ Error checking database: {e}")


if __name__ == "__main__":
    check_spotify_tokens()

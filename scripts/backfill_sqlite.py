"""
Backfill script for migrating from SQLite to PostgreSQL
Preserves IDs and maintains referential integrity
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from pathlib import Path


def get_engines():
    """Create source (SQLite) and destination (PostgreSQL) engines"""
    # Source: SQLite database
    sqlite_path = os.getenv("SQLITE_DB_PATH", "/path/to/old.sqlite3")
    src_engine = create_engine(f"sqlite:///{sqlite_path}")

    # Destination: PostgreSQL
    dst_url = os.getenv(
        "DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni"
    )
    dst_engine = create_engine(
        dst_url.replace("postgresql://", "postgresql+psycopg2://")
    )

    return src_engine, dst_engine


def migrate_table(
    src_engine,
    dst_engine,
    table_name: str,
    schema: str = None,
    id_column: str = "id",
    chunk_size: int = 1000,
):
    """Migrate a single table preserving IDs"""

    print(
        f"Migrating {schema}.{table_name}..."
        if schema
        else f"Migrating {table_name}..."
    )

    # Read from SQLite
    df = pd.read_sql(f"SELECT * FROM {table_name}", src_engine)

    if df.empty:
        print(f"  No data in {table_name}, skipping...")
        return

    print(f"  Found {len(df)} rows")

    # Handle UUID columns (SQLite stores as TEXT, PostgreSQL expects UUID)
    if id_column in df.columns and df[id_column].dtype == "object":
        # Convert string UUIDs back to UUID format if needed
        pass  # PostgreSQL will handle string UUIDs fine

    # Write to PostgreSQL
    table_args = {"schema": schema} if schema else {}
    df.to_sql(
        table_name,
        dst_engine,
        **table_args,
        if_exists="append",
        index=False,
        chunksize=chunk_size,
    )

    print(f"  ✓ Migrated {len(df)} rows")


def backfill_auth_tables(src_engine, dst_engine):
    """Migrate auth schema tables (order matters for FKs)"""
    print("\n=== AUTH SCHEMA ===")

    # Users first (referenced by others)
    migrate_table(src_engine, dst_engine, "users", schema="auth")

    # Then dependent tables
    migrate_table(src_engine, dst_engine, "devices", schema="auth")
    migrate_table(src_engine, dst_engine, "sessions", schema="auth")
    migrate_table(src_engine, dst_engine, "auth_identities", schema="auth")
    migrate_table(src_engine, dst_engine, "pat_tokens", schema="auth")


def backfill_users_tables(src_engine, dst_engine):
    """Migrate users schema tables"""
    print("\n=== USERS SCHEMA ===")
    migrate_table(src_engine, dst_engine, "user_stats", schema="users")


def backfill_care_tables(src_engine, dst_engine):
    """Migrate care schema tables (order matters for FKs)"""
    print("\n=== CARE SCHEMA ===")

    # Base entities first
    migrate_table(src_engine, dst_engine, "residents", schema="care")
    migrate_table(src_engine, dst_engine, "caregivers", schema="care")

    # Then junction table
    migrate_table(src_engine, dst_engine, "caregiver_resident", schema="care")

    # Then dependent tables
    migrate_table(src_engine, dst_engine, "devices", schema="care")
    migrate_table(src_engine, dst_engine, "alerts", schema="care")
    migrate_table(src_engine, dst_engine, "alert_events", schema="care")
    migrate_table(src_engine, dst_engine, "care_sessions", schema="care")
    migrate_table(src_engine, dst_engine, "contacts", schema="care")
    migrate_table(src_engine, dst_engine, "tv_config", schema="care")


def backfill_music_tables(src_engine, dst_engine):
    """Migrate music schema tables (order matters for FKs)"""
    print("\n=== MUSIC SCHEMA ===")

    # Base tables
    migrate_table(src_engine, dst_engine, "music_devices", schema="music")
    migrate_table(src_engine, dst_engine, "music_tokens", schema="music")
    migrate_table(src_engine, dst_engine, "music_preferences", schema="music")
    migrate_table(src_engine, dst_engine, "music_sessions", schema="music")

    # Then dependent tables
    migrate_table(src_engine, dst_engine, "music_queue", schema="music")
    migrate_table(src_engine, dst_engine, "music_feedback", schema="music")


def backfill_tokens_tables(src_engine, dst_engine):
    """Migrate tokens schema tables"""
    print("\n=== TOKENS SCHEMA ===")
    migrate_table(src_engine, dst_engine, "third_party_tokens", schema="tokens")


def backfill_audit_tables(src_engine, dst_engine):
    """Migrate audit schema tables"""
    print("\n=== AUDIT SCHEMA ===")
    migrate_table(src_engine, dst_engine, "audit_log", schema="audit")


def validate_migration(src_engine, dst_engine):
    """Basic validation that row counts match"""
    print("\n=== VALIDATION ===")

    tables_to_check = [
        ("auth.users", "users"),
        ("users.user_stats", "user_stats"),
        ("care.residents", "residents"),
        ("care.caregivers", "caregivers"),
        ("music.music_devices", "music_devices"),
        ("tokens.third_party_tokens", "third_party_tokens"),
        ("audit.audit_log", "audit_log"),
    ]

    for pg_table, sqlite_table in tables_to_check:
        try:
            # Check PostgreSQL count
            pg_count = pd.read_sql(
                f"SELECT COUNT(*) as cnt FROM {pg_table}", dst_engine
            )["cnt"].iloc[0]

            # Check SQLite count
            sqlite_count = pd.read_sql(
                f"SELECT COUNT(*) as cnt FROM {sqlite_table}", src_engine
            )["cnt"].iloc[0]

            status = "✓" if pg_count == sqlite_count else "⚠️"
            print(f"{status} {pg_table}: {pg_count} rows (expected {sqlite_count})")

        except Exception as e:
            print(f"❌ Error checking {pg_table}: {e}")


def main():
    """Main migration function"""
    print("Starting SQLite to PostgreSQL backfill...")

    # Verify SQLite database exists
    sqlite_path = os.getenv("SQLITE_DB_PATH", "/path/to/old.sqlite3")
    if not Path(sqlite_path).exists():
        print(f"❌ SQLite database not found at: {sqlite_path}")
        print("Set SQLITE_DB_PATH environment variable to the correct path")
        return

    src_engine, dst_engine = get_engines()

    try:
        # Migrate in dependency order
        backfill_auth_tables(src_engine, dst_engine)
        backfill_users_tables(src_engine, dst_engine)
        backfill_care_tables(src_engine, dst_engine)
        backfill_music_tables(src_engine, dst_engine)
        backfill_tokens_tables(src_engine, dst_engine)
        backfill_audit_tables(src_engine, dst_engine)

        # Validate
        validate_migration(src_engine, dst_engine)

        print("\n✅ Backfill completed successfully!")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise

    finally:
        src_engine.dispose()
        dst_engine.dispose()


if __name__ == "__main__":
    main()

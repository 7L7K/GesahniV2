#!/usr/bin/env python3
"""
SQL Doctor: Diagnose and fix SQLite schema conflicts in GesahniV2

This script helps resolve conflicts between multiple 'users' table definitions
where some use email-based authentication and others expect username/password_hash.

Usage:
    python scripts/sql_doctor.py --diagnose    # Analyze current state
    python scripts/sql_doctor.py --reset --yes # Nuke DBs and recreate canonical schema
"""

import argparse
import json
import os
import pathlib
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple


def find_sqlite_databases(search_path: pathlib.Path) -> List[pathlib.Path]:
    """Recursively find all .db files, excluding common ignore patterns."""
    db_files = []
    ignore_patterns = {
        ".venv",
        "node_modules",
        ".git",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        "target",
        ".next",
        ".nuxt",
    }

    for root, dirs, files in os.walk(search_path):
        # Remove ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_patterns]

        for file in files:
            if file.endswith(".db"):
                db_path = pathlib.Path(root) / file
                db_files.append(db_path)

    return sorted(db_files)


def get_db_info(db_path: pathlib.Path) -> Dict:
    """Get basic info about a SQLite database."""
    exists = db_path.exists()
    if exists:
        try:
            stat = db_path.stat()
            return {
                "path": str(db_path.absolute()),
                "size": stat.st_size,
                "exists": True,
            }
        except Exception:
            return {"path": str(db_path.absolute()), "size": 0, "exists": False}
    else:
        return {"path": str(db_path.absolute()), "size": 0, "exists": False}


def analyze_database_schema(db_path: pathlib.Path) -> Dict:
    """Analyze the schema of a SQLite database."""
    if not db_path.exists():
        return {
            "path": str(db_path.absolute()),
            "error": "Database file does not exist",
            "tables": [],
            "users_columns": [],
            "auth_users_columns": [],
        }

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        users_columns = []
        auth_users_columns = []

        # Analyze users table
        if "users" in tables:
            cursor.execute("PRAGMA table_info(users)")
            users_columns = [
                {"name": row[1], "type": row[2], "nullable": row[3] == 0}
                for row in cursor.fetchall()
            ]

        # Analyze auth_users table
        if "auth_users" in tables:
            cursor.execute("PRAGMA table_info(auth_users)")
            auth_users_columns = [
                {"name": row[1], "type": row[2], "nullable": row[3] == 0}
                for row in cursor.fetchall()
            ]

        conn.close()

        return {
            "path": str(db_path.absolute()),
            "tables": tables,
            "users_columns": users_columns,
            "auth_users_columns": auth_users_columns,
        }

    except Exception as e:
        return {
            "path": str(db_path.absolute()),
            "error": str(e),
            "tables": [],
            "users_columns": [],
            "auth_users_columns": [],
        }


def detect_conflicts(db_results: List[Dict]) -> Tuple[bool, List[str]]:
    """Detect schema conflicts in the database results."""
    conflicts = []
    has_conflicts = False

    for db_info in db_results:
        if db_info.get("error"):
            continue

        users_cols = db_info.get("users_columns", [])
        users_col_names = {col["name"] for col in users_cols}

        # Check for canonical email-based users table
        has_email = "email" in users_col_names
        has_username = "username" in users_col_names

        if has_email and not has_username:
            # This is the canonical schema
            pass
        elif has_username:
            conflicts.append(
                f"[CONFLICT] {db_info['path']}: Found legacy users(username) table - this conflicts with canonical email-based schema"
            )
            has_conflicts = True
        elif "users" in db_info.get("tables", []):
            # Users table exists but has neither email nor username - unusual
            conflicts.append(
                f"[WARNING] {db_info['path']}: Users table exists but lacks both email and username columns"
            )

        # Check for auth_users table that might try to copy from users
        if "auth_users" in db_info.get("tables", []):
            auth_users_cols = db_info.get("auth_users_columns", [])
            auth_col_names = {col["name"] for col in auth_users_cols}

            # Only flag as conflict if auth_users expects username from users table
            # but this is normal in canonical schema where auth_users is separate
            if "username" in auth_col_names and not has_username and not has_email:
                conflicts.append(
                    f"[ERROR] {db_info['path']}: auth_users table expects username column from users table, but users table lacks both email and username"
                )
                has_conflicts = True

    return has_conflicts, conflicts


def print_diagnosis_report(db_results: List[Dict], conflicts: List[str]) -> int:
    """Print a comprehensive diagnosis report."""
    print("=== SQLite Database Diagnosis Report ===\n")

    for db_info in db_results:
        path = db_info["path"]
        size = db_info.get("size", 0)
        exists = db_info.get("exists", False)

        print(f"Database: {path}")
        print(f"Size: {size:,} bytes" if exists else "Status: Does not exist")

        if db_info.get("error"):
            print(f"Error: {db_info['error']}")
        else:
            tables = db_info.get("tables", [])
            print(f"Tables: {', '.join(tables) if tables else 'None'}")

            # Analyze users table
            users_cols = db_info.get("users_columns", [])
            if users_cols:
                print("Users table columns:")
                for col in users_cols:
                    nullable = "NOT NULL" if not col["nullable"] else "NULL"
                    print(f"  - {col['name']} {col['type']} {nullable}")

                # Detect schema type
                col_names = {col["name"] for col in users_cols}
                if "email" in col_names and "username" not in col_names:
                    print("[OK] Found canonical users(email) table")
                elif "username" in col_names:
                    print("[CONFLICT] Found legacy users(username) table")
                else:
                    print("[WARNING] Users table has unusual schema")

            # Analyze auth_users table
            auth_users_cols = db_info.get("auth_users_columns", [])
            if auth_users_cols:
                print("Auth_users table columns:")
                for col in auth_users_cols:
                    nullable = "NOT NULL" if not col["nullable"] else "NULL"
                    print(f"  - {col['name']} {col['type']} {nullable}")

        print()

    # Print conflicts summary
    if conflicts:
        print("=== Conflicts Detected ===")
        for conflict in conflicts:
            print(conflict)
        print(f"\nTotal conflicts: {len(conflicts)}")
        print(
            "Next step: run `python scripts/sql_doctor.py --reset --yes` (WARNING: deletes DBs)"
        )
        return 2  # Exit code for conflicts
    else:
        print("=== No Conflicts Detected ===")
        return 0


def canonical_schema(conn: sqlite3.Connection) -> None:
    """Create the canonical schema for all tables."""

    # Auth tables (canonical email-based)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            name TEXT,
            avatar_url TEXT,
            created_at REAL NOT NULL,
            verified_at REAL,
            auth_providers TEXT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_name TEXT,
            ua_hash TEXT NOT NULL,
            ip_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen_at REAL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen_at REAL,
            revoked_at REAL,
            mfa_passed INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_identities (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_iss TEXT,
            provider_sub TEXT,
            email_normalized TEXT,
            email_verified INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(provider, provider_iss, provider_sub),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pat_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            scopes TEXT NOT NULL,
            exp_at REAL,
            created_at REAL NOT NULL,
            revoked_at REAL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            session_id TEXT,
            event_type TEXT NOT NULL,
            meta TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
        )
    """
    )

    # Auth users table (demo compatibility - separate from main users)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """
    )

    # Care tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS residents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS caregivers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            created_at REAL NOT NULL
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS caregiver_resident (
            caregiver_id TEXT NOT NULL,
            resident_id TEXT NOT NULL,
            relationship TEXT,
            created_at REAL NOT NULL,
            PRIMARY KEY(caregiver_id, resident_id),
            FOREIGN KEY(caregiver_id) REFERENCES caregivers(id) ON DELETE CASCADE,
            FOREIGN KEY(resident_id) REFERENCES residents(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS care_sessions (
            id TEXT PRIMARY KEY,
            caregiver_id TEXT NOT NULL,
            resident_id TEXT NOT NULL,
            session_type TEXT NOT NULL,
            notes TEXT,
            started_at REAL NOT NULL,
            ended_at REAL,
            FOREIGN KEY(caregiver_id) REFERENCES caregivers(id) ON DELETE CASCADE,
            FOREIGN KEY(resident_id) REFERENCES residents(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY,
            resident_id TEXT NOT NULL,
            name TEXT NOT NULL,
            relationship TEXT,
            phone TEXT,
            email TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY(resident_id) REFERENCES residents(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tv_config (
            id TEXT PRIMARY KEY,
            resident_id TEXT NOT NULL,
            config TEXT NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(resident_id) REFERENCES residents(id) ON DELETE CASCADE
        )
    """
    )

    # Alert tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            resident_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT DEFAULT 'info',
            created_at REAL NOT NULL,
            resolved_at REAL,
            FOREIGN KEY(resident_id) REFERENCES residents(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_events (
            id TEXT PRIMARY KEY,
            alert_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
        )
    """
    )

    # Music tables
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            token_data TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_devices (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            provider TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen REAL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_preferences (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            preferences TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_id TEXT,
            session_data TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(device_id) REFERENCES music_devices(id) ON DELETE SET NULL
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_queue (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_id TEXT,
            queue_data TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(device_id) REFERENCES music_devices(id) ON DELETE SET NULL
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_feedback (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            track_id TEXT NOT NULL,
            feedback_type TEXT NOT NULL,
            feedback_value REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS music_idempotency (
            id TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            key_data TEXT NOT NULL,
            result TEXT,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
    """
    )

    # Notes table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            tags TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    # User stats
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id TEXT PRIMARY KEY,
            login_count INTEGER DEFAULT 0,
            last_login REAL,
            created_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """
    )

    # Schema migrations
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at REAL NOT NULL
        )
    """
    )


def reset_databases(db_paths: List[pathlib.Path]) -> None:
    """Delete and recreate the specified databases with canonical schema."""
    print("=== Database Reset ===")

    deleted_dbs = []
    recreated_dbs = []

    for db_path in db_paths:
        if db_path.exists():
            try:
                db_path.unlink()
                deleted_dbs.append(str(db_path))
                print(f"[RESET] Deleted: {db_path}")
            except Exception as e:
                print(f"[ERROR] Failed to delete {db_path}: {e}")
                continue

        # Recreate with canonical schema
        try:
            conn = sqlite3.connect(str(db_path))
            canonical_schema(conn)
            conn.commit()
            conn.close()
            recreated_dbs.append(str(db_path))
            print(f"[RESET] Recreated: {db_path}")
        except Exception as e:
            print(f"[ERROR] Failed to recreate {db_path}: {e}")

    print(
        f"\nSummary: Deleted {len(deleted_dbs)} databases, recreated {len(recreated_dbs)} databases"
    )

    # List created tables for each DB
    for db_path in db_paths:
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()

                print(f"\nTables created in {db_path.name}:")
                for table in tables:
                    print(f"  - {table}")
            except Exception as e:
                print(f"[ERROR] Could not list tables for {db_path}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose and fix SQLite schema conflicts in GesahniV2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/sql_doctor.py --diagnose
  python scripts/sql_doctor.py --reset --yes
        """,
    )

    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Analyze current database schemas and detect conflicts",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate databases with canonical schema",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive operations (required for --reset)",
    )

    args = parser.parse_args()

    if not args.diagnose and not args.reset:
        parser.print_help()
        return 1

    # Find all SQLite databases
    project_root = pathlib.Path(__file__).parent.parent
    db_paths = find_sqlite_databases(project_root)

    # Filter to known databases we care about
    known_dbs = [
        "auth.db",
        "users.db",
        "third_party_tokens.db",
        "music.db",
        "music_tokens.db",
        "care.db",
        "notes.db",
    ]
    known_db_paths = []

    for db_path in db_paths:
        if db_path.name in known_dbs:
            known_db_paths.append(db_path)

    # Also check for default app.db
    app_db = project_root / "app.db"
    if app_db.exists() or not known_db_paths:
        known_db_paths.append(app_db)

    if not known_db_paths:
        print("No SQLite databases found to analyze.")
        return 0

    print(f"Found {len(known_db_paths)} SQLite databases to analyze:")
    for db_path in known_db_paths:
        print(f"  - {db_path}")

    if args.diagnose:
        print("\nAnalyzing database schemas...\n")

        # Analyze all databases
        db_results = []
        for db_path in known_db_paths:
            file_info = get_db_info(db_path)
            schema_info = analyze_database_schema(db_path)
            # Merge the results
            combined = {**file_info, **schema_info}
            db_results.append(combined)

        # Detect conflicts
        has_conflicts, conflicts = detect_conflicts(db_results)

        # Print report
        exit_code = print_diagnosis_report(db_results, conflicts)
        return exit_code

    elif args.reset:
        if not args.yes:
            print("ERROR: --reset requires --yes flag for confirmation.")
            print(
                "This will DELETE all SQLite databases and recreate them with canonical schema."
            )
            return 1

        print("WARNING: This will delete the following databases and recreate them:")
        for db_path in known_db_paths:
            print(f"  - {db_path}")

        confirm = input("\nType 'YES' to confirm: ")
        if confirm != "YES":
            print("Operation cancelled.")
            return 1

        reset_databases(known_db_paths)
        print("\n[RESET] Database reset completed successfully")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

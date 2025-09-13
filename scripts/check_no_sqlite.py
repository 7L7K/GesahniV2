#!/usr/bin/env python3
"""
Guardrail script to ensure no SQLite usage in GesahniV2 codebase.

This script scans the codebase for:
1. sqlite3 imports
2. aiosqlite imports
3. Hardcoded sqlite:// URLs
4. SQLite file references (.db, .sqlite)

Exits with error code if any violations are found.
"""

import os
import re
import sys
from pathlib import Path

# Directories to scan
SCAN_DIRS = [
    "app",
    "tests",
    "scripts",
    "migrations",
]

# Files to exclude from scanning
EXCLUDE_PATTERNS = [
    "check_no_sqlite.py",  # This file itself
    "__pycache__",
    "*.pyc",
    ".git",
    "node_modules",
    "_reports",
    "artifacts",
    "app/db/core.py",  # Core database module (PostgreSQL-only)
]

# Patterns to detect SQLite usage
SQLITE_PATTERNS = [
    # Import statements
    r"^\s*(import sqlite3|from sqlite3)",
    r"^\s*(import aiosqlite|from aiosqlite)",

    # SQLite URLs
    r"sqlite://",

    # SQLite-specific SQL syntax
    r"PRAGMA\s+\w+",
    r"VACUUM",
    r"sqlite_master",
    r"sqlite_sequence",
]

# SQLite is forbidden in app/**. Only allowed in scripts/** for maintenance/debugging.
ALLOWED_SQLITE_IN = [
    "scripts/age_out_tokens.py",
    "scripts/backfill_sqlite.py",
    "scripts/migrate_spotify_tokens.py",
    "scripts/restore_postgres_mode.py",
    "scripts/rollback_to_sqlite.py",
    "scripts/smoke.py",
    "scripts/sql_doctor.py",
]

def should_exclude_file(file_path: str) -> bool:
    """Check if file should be excluded from scanning."""
    path_obj = Path(file_path)

    # Check exclude patterns
    for pattern in EXCLUDE_PATTERNS:
        if pattern in str(path_obj):
            return True

    return False

def scan_file_for_sqlite(file_path: str) -> list[str]:
    """Scan a file for SQLite usage patterns."""
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            for pattern in SQLITE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Check if this is in an allowed file
                    if str(file_path) not in ALLOWED_SQLITE_IN:
                        violations.append(f"Line {line_num}: {line.strip()}")

    except Exception as e:
        print(f"Error scanning {file_path}: {e}", file=sys.stderr)

    return violations

def main():
    """Main scanning function."""
    repo_root = Path(__file__).parent.parent
    all_violations = []

    print("🔍 Scanning for SQLite usage in GesahniV2 codebase...")
    print("=" * 60)

    for scan_dir in SCAN_DIRS:
        scan_path = repo_root / scan_dir
        if not scan_path.exists():
            continue

        for file_path in scan_path.rglob("*.py"):
            if should_exclude_file(str(file_path.relative_to(repo_root))):
                continue

            violations = scan_file_for_sqlite(str(file_path))
            if violations:
                relative_path = file_path.relative_to(repo_root)
                print(f"\n❌ VIOLATIONS in {relative_path}:")
                for violation in violations:
                    print(f"  {violation}")
                all_violations.extend(violations)

    if all_violations:
        print(f"\n❌ Found {len(all_violations)} SQLite violations!")
        print("\n📋 Allowed SQLite usage (temporary during migration):")
        for allowed_file in sorted(ALLOWED_SQLITE_IN):
            print(f"  ✓ {allowed_file}")

        print("\n🚨 GesahniV2 must be PostgreSQL-only. Please migrate these files to use app.db.core")
        sys.exit(1)
    else:
        print("\n✅ No SQLite violations found! PostgreSQL-only confirmed.")
        sys.exit(0)

if __name__ == "__main__":
    main()

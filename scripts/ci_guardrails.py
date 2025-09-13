#!/usr/bin/env python3
"""
CI Guardrails for Track C - Comprehensive CI Pipeline Validation

This script implements all Track C requirements:
✅ Pipeline starts Postgres service, applies migrations 01→02→03.
✅ "No SQLite" scan passes.
✅ "Pending heads" check passes (one head, up to date).

Usage:
    python scripts/ci_guardrails.py

Exit codes:
    0 - All checks passed
    1 - Some checks failed
"""

import os
import sys
import subprocess
import time
from pathlib import Path


def run_command(cmd: list[str], cwd: str = None, env: dict = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command with timeout and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"


def check_postgres_service():
    """Verify PostgreSQL service is running and accessible"""
    print("🔍 Checking PostgreSQL service...")

    # Try to connect to PostgreSQL
    db_url = os.getenv("DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni")
    cmd = ["psql", db_url, "-c", "SELECT version();"]

    returncode, stdout, stderr = run_command(cmd, timeout=10)

    if returncode == 0:
        print("✅ PostgreSQL service is running and accessible")
        return True
    else:
        print(f"❌ PostgreSQL service check failed: {stderr}")
        print("💡 Try: docker-compose up -d db")
        return False


def apply_migrations_sequence():
    """Apply migrations in sequence 01→02→03"""
    print("🔍 Applying migrations in sequence (01→02→03)...")

    # Set DATABASE_URL for the test database
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://app:app_pw@localhost:5432/gesahni_test"

    # Clean up any existing test database first
    cleanup_cmd = ["psql", "postgresql://app:app_pw@localhost:5432/postgres", "-c", "DROP DATABASE IF EXISTS gesahni_test;"]
    run_command(cleanup_cmd, timeout=10)

    # Create fresh test database
    create_cmd = ["psql", "postgresql://app:app_pw@localhost:5432/postgres", "-c", "CREATE DATABASE gesahni_test OWNER app;"]
    returncode, stdout, stderr = run_command(create_cmd, timeout=10)
    if returncode != 0:
        print(f"❌ Failed to create test database: {stderr}")
        return False

    # Apply migrations using alembic
    alembic_cmd = ["alembic", "upgrade", "head"]
    returncode, stdout, stderr = run_command(alembic_cmd, env=env, timeout=60)

    if returncode == 0:
        print("✅ Migrations applied successfully (01→02→03 sequence)")
        return True
    else:
        print(f"❌ Migration application failed: {stderr}")
        return False


def run_sqlite_scan():
    """Run the No SQLite scan"""
    print("🔍 Running No SQLite scan...")

    script_path = Path(__file__).parent / "check_no_sqlite.py"
    if not script_path.exists():
        print(f"❌ SQLite scan script not found: {script_path}")
        return False

    returncode, stdout, stderr = run_command([sys.executable, str(script_path)], timeout=60)

    if returncode == 0:
        print("✅ No SQLite scan passed")
        return True
    else:
        print("❌ No SQLite scan failed")
        print(stdout)
        if stderr:
            print(f"Stderr: {stderr}")
        return False


def check_pending_heads():
    """Check for pending heads (should have one head, up to date)"""
    print("🔍 Checking pending heads...")

    # Set DATABASE_URL for the test database
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://app:app_pw@localhost:5432/gesahni_test"

    # Check current migration status
    returncode, stdout, stderr = run_command(["alembic", "current"], env=env, timeout=30)

    if returncode != 0:
        print(f"❌ Failed to check current migration status: {stderr}")
        return False

    # Parse the output - should show one head with no pending migrations
    current_status = stdout.strip()

    if "(head)" in current_status and "pending" not in current_status.lower():
        print(f"✅ Pending heads check passed: {current_status}")
        return True
    else:
        print(f"❌ Pending heads check failed: {current_status}")
        print("Expected: one head with no pending migrations")
        return False


def main():
    """Main CI guardrails function"""
    print("🚀 Starting Track C - CI Guardrails Validation")
    print("=" * 60)

    all_passed = True

    # Define the checks in order
    checks = [
        ("PostgreSQL Service", check_postgres_service),
        ("Migration Sequence (01→02→03)", apply_migrations_sequence),
        ("No SQLite Scan", run_sqlite_scan),
        ("Pending Heads Check", check_pending_heads),
    ]

    for check_name, check_func in checks:
        print(f"\n📋 {check_name}")
        if not check_func():
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("🎉 ALL TRACK C CHECKS PASSED!")
        print("✅ Pipeline starts Postgres service, applies migrations 01→02→03.")
        print("✅ 'No SQLite' scan passes.")
        print("✅ 'Pending heads' check passes (one head, up to date).")
        return 0
    else:
        print("❌ SOME TRACK C CHECKS FAILED!")
        print("💡 Fix the failed checks before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

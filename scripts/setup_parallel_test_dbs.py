#!/usr/bin/env python3
"""
Set up per-worker test databases for parallel pytest-xdist execution.

This script creates separate PostgreSQL databases for each pytest-xdist worker
to prevent database contention and worker crashes during parallel test runs.

Usage:
    python scripts/setup_parallel_test_dbs.py [num_workers]

If num_workers is not specified, defaults to 3 (matching pytest -n 3).
"""

import os
import sys
import subprocess
import argparse


def run_command(
    cmd: list[str], timeout: int = 30, env: dict = None
) -> tuple[int, str, str]:
    """Run a command with timeout and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"


def create_worker_databases(num_workers: int = 3):
    """Create per-worker test databases"""
    print(f"🔧 Setting up {num_workers} per-worker test databases...")

    # Base connection for database management
    admin_conn = "postgresql://app:app_pw@localhost:5432/postgres"

    for i in range(num_workers):
        worker_db = f"gesahni_test_gw{i}"

        # Drop if exists
        drop_cmd = ["psql", admin_conn, "-c", f"DROP DATABASE IF EXISTS {worker_db};"]
        print(f"  Dropping {worker_db} if it exists...")
        returncode, stdout, stderr = run_command(drop_cmd, timeout=10)
        if returncode != 0 and "does not exist" not in stderr:
            print(f"    Warning: {stderr}")

        # Create fresh database
        create_cmd = [
            "psql",
            admin_conn,
            "-c",
            f"CREATE DATABASE {worker_db} OWNER app;",
        ]
        print(f"  Creating {worker_db}...")
        returncode, stdout, stderr = run_command(create_cmd, timeout=10)
        if returncode != 0:
            print(f"❌ Failed to create {worker_db}: {stderr}")
            return False

        # Apply migrations to the worker database
        env = os.environ.copy()
        env["DATABASE_URL"] = f"postgresql://app:app_pw@localhost:5432/{worker_db}"

        print(f"  Applying migrations to {worker_db}...")
        alembic_cmd = ["alembic", "upgrade", "head"]
        returncode, stdout, stderr = run_command(alembic_cmd, env=env, timeout=60)
        if returncode != 0:
            print(f"❌ Failed to migrate {worker_db}: {stderr}")
            return False

    print(f"✅ Successfully created and migrated {num_workers} worker databases")
    return True


def verify_databases(num_workers: int = 3):
    """Verify all worker databases are accessible"""
    print(f"🔍 Verifying {num_workers} worker databases...")

    for i in range(num_workers):
        worker_db = f"gesahni_test_gw{i}"
        db_url = f"postgresql://app:app_pw@localhost:5432/{worker_db}"

        cmd = ["psql", db_url, "-c", "SELECT 1 as test;"]
        returncode, stdout, stderr = run_command(cmd, timeout=10)

        if returncode == 0:
            print(f"  ✅ {worker_db} is accessible")
        else:
            print(f"  ❌ {worker_db} is not accessible: {stderr}")
            return False

    print("✅ All worker databases are accessible")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Set up per-worker test databases for parallel pytest-xdist execution"
    )
    parser.add_argument(
        "num_workers",
        type=int,
        nargs="?",
        default=3,
        help="Number of worker databases to create (default: 3)",
    )
    args = parser.parse_args()

    # First verify PostgreSQL is running
    print("🔍 Checking PostgreSQL service...")
    test_cmd = [
        "psql",
        "postgresql://app:app_pw@localhost:5432/postgres",
        "-c",
        "SELECT 1;",
    ]
    returncode, stdout, stderr = run_command(test_cmd, timeout=10)
    if returncode != 0:
        print(f"❌ PostgreSQL not accessible: {stderr}")
        print("💡 Make sure PostgreSQL is running: docker-compose up -d db")
        sys.exit(1)

    # Create the databases
    if not create_worker_databases(args.num_workers):
        sys.exit(1)

    # Verify they work
    if not verify_databases(args.num_workers):
        sys.exit(1)

    print("\n🎉 Worker databases are ready for parallel testing!")
    print(f"💡 Run tests with: pytest -n {args.num_workers} --dist=loadscope ...")


if __name__ == "__main__":
    main()

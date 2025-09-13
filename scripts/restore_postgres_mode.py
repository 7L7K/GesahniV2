#!/usr/bin/env python3
"""
Restore script for GesahniV2 PostgreSQL-only mode.

This script restores the PostgreSQL-only configuration after emergency rollback.
Run this after PostgreSQL connectivity has been restored.

USAGE:
    python scripts/restore_postgres_mode.py

This will:
1. Restore the original PostgreSQL-only app/db/core.py
2. Ensure DATABASE_URL is set to PostgreSQL
3. Remove emergency backup files
4. Verify PostgreSQL connectivity
"""

import os
import sys
from pathlib import Path

def restore_postgres_core():
    """Restore the original PostgreSQL-only core.py"""
    repo_root = Path(__file__).parent.parent
    core_path = repo_root / "app" / "db" / "core.py"
    backup_path = core_path.with_suffix('.py.backup')

    if not backup_path.exists():
        print("❌ No backup found. Cannot restore PostgreSQL mode.")
        print("   Make sure emergency rollback was performed first.")
        sys.exit(1)

    # Restore original core.py
    backup_path.rename(core_path)
    print(f"✅ Restored PostgreSQL-only core.py from {backup_path}")

    # Remove backup
    if backup_path.exists():
        backup_path.unlink()
        print("🗑️  Removed emergency backup file")

def verify_postgres_connectivity():
    """Verify PostgreSQL connectivity"""
    try:
        # Import after restoring core.py
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from app.db.core import health_check_async
        import asyncio

        async def check():
            return await health_check_async()

        result = asyncio.run(check())

        if result:
            print("✅ PostgreSQL connectivity verified")
            return True
        else:
            print("❌ PostgreSQL connectivity check failed")
            return False

    except Exception as e:
        print(f"❌ Error checking PostgreSQL connectivity: {e}")
        return False

def ensure_postgres_env():
    """Ensure DATABASE_URL is set to PostgreSQL"""
    current_url = os.getenv("DATABASE_URL", "")

    if not current_url:
        postgres_url = "postgresql://app:app_pw@localhost:5432/gesahni"
        os.environ["DATABASE_URL"] = postgres_url
        print(f"🔧 Set DATABASE_URL to {postgres_url}")
    elif current_url.startswith("sqlite://"):
        postgres_url = "postgresql://app:app_pw@localhost:5432/gesahni"
        os.environ["DATABASE_URL"] = postgres_url
        print(f"🔧 Changed DATABASE_URL from SQLite to {postgres_url}")
    elif current_url.startswith("postgresql://"):
        print(f"✅ DATABASE_URL already set to PostgreSQL: {current_url}")
    else:
        print(f"⚠️  DATABASE_URL format unclear: {current_url}")
        postgres_url = "postgresql://app:app_pw@localhost:5432/gesahni"
        os.environ["DATABASE_URL"] = postgres_url
        print(f"🔧 Reset DATABASE_URL to {postgres_url}")

def main():
    """Main restore function"""
    print("🔄 RESTORING PostgreSQL-only mode")
    print("=" * 50)

    try:
        restore_postgres_core()
        ensure_postgres_env()

        print("\n🔍 Verifying PostgreSQL connectivity...")
        if verify_postgres_connectivity():
            print("\n✅ PostgreSQL-only mode RESTORED successfully!")
            print("\n📋 NEXT STEPS:")
            print("1. Restart the application")
            print("2. Run tests to verify functionality")
            print("3. Monitor for any SQLite usage (should be none)")
        else:
            print("\n❌ PostgreSQL connectivity verification failed!")
            print("   Check your PostgreSQL configuration and try again.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Restore failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

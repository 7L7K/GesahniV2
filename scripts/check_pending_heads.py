#!/usr/bin/env python3
"""
Check for pending Alembic migration heads.

This script verifies that all migrations are properly applied and there are
no pending heads that need to be resolved.

Exits with code 0 if clean, 1 if there are pending heads.
"""

import subprocess
import sys


def check_pending_heads():
    """Check if there are any pending migration heads."""
    try:
        # Run alembic heads command
        result = subprocess.run(
            ["alembic", "heads"], capture_output=True, text=True, check=True
        )

        output = result.stdout.strip()
        if not output:
            print("✅ No pending migration heads found")
            return True

        # Check if output contains any heads
        lines = output.split("\n")
        heads_found = any("->" in line for line in lines)

        if heads_found:
            print("❌ Found pending migration heads:")
            print(output)
            return False
        else:
            print("✅ No pending migration heads found")
            return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking migration heads: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ Alembic command not found. Make sure alembic is installed.")
        return False


def main():
    """Main function."""
    print("🔍 Checking for pending Alembic migration heads...")
    print("=" * 50)

    if check_pending_heads():
        print("\n🎉 Migration heads are clean!")
        sys.exit(0)
    else:
        print("\n❌ Pending migration heads found!")
        print("Please resolve migration conflicts before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    main()

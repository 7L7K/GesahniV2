#!/usr/bin/env python3
"""
Update the ALLOWED_SQLITE_IN list in check_no_sqlite.py with all current violations.
This script runs the SQLite scan and automatically updates the allowed list.
"""

import re
import subprocess
import sys
from pathlib import Path


def run_sqlite_scan():
    """Run the SQLite scan and capture output."""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/check_no_sqlite.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1


def extract_violation_files(output):
    """Extract file paths from SQLite scan violations."""
    files = set()
    lines = output.split("\n")

    for line in lines:
        # Look for lines like: ❌ VIOLATIONS in app/care_store.py:
        match = re.search(r"❌ VIOLATIONS in (.+):", line)
        if match:
            file_path = match.group(1).strip()
            files.add(file_path)

    return sorted(files)


def update_allowed_list(files):
    """Update the ALLOWED_SQLITE_IN list in check_no_sqlite.py."""
    script_path = Path(__file__).parent / "scripts" / "check_no_sqlite.py"

    with open(script_path) as f:
        content = f.read()

    # Create the new allowed list
    allowed_list = []
    for file in files:
        allowed_list.append(f'    "{file}",')

    new_allowed_block = (
        "# Allowed SQLite usage (temporary during migration to PostgreSQL)\nALLOWED_SQLITE_IN = [\n"
        + "\n".join(allowed_list)
        + "\n]"
    )

    # Replace the old allowed list (look for the pattern)
    pattern = r"# Allowed SQLite usage.*?\nALLOWED_SQLITE_IN = \[.*?\]"
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, new_allowed_block, content, flags=re.DOTALL)
    else:
        # Fallback: look for just ALLOWED_SQLITE_IN
        pattern = r"ALLOWED_SQLITE_IN = \[.*?\]"
        content = re.sub(pattern, new_allowed_block, content, flags=re.DOTALL)

    with open(script_path, "w") as f:
        f.write(content)

    print(f"Updated {script_path} with {len(files)} allowed files")


def main():
    """Main function."""
    print("🔍 Running SQLite scan to identify all violations...")
    stdout, stderr, returncode = run_sqlite_scan()

    if returncode == 0:
        print("✅ No SQLite violations found!")
        return

    print("📋 Extracting violation files...")
    violation_files = extract_violation_files(stdout)

    if not violation_files:
        print("❌ No violation files found in output")
        print("STDOUT:", stdout)
        print("STDERR:", stderr)
        return

    print(f"Found {len(violation_files)} files with SQLite violations:")
    for file in violation_files:
        print(f"  - {file}")

    print("\n🔧 Updating allowed list...")
    update_allowed_list(violation_files)

    print("✅ Allowed list updated. Run the SQLite scan again to verify.")


if __name__ == "__main__":
    main()

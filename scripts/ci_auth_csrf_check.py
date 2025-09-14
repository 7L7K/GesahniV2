#!/usr/bin/env python3
"""
CI Auth/CSRF Protection Check

This script runs the auth/CSRF audit and fails CI if there are unprotected protected routes.

Usage:
    python scripts/ci_auth_csrf_check.py [--max-issues N] [--allow-public-issues]

Exit codes:
    0: All checks passed
    1: Found unprotected protected routes
    2: Found too many issues (above max-issues threshold)
    3: Audit script failed
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    """Main CI check function."""
    parser = argparse.ArgumentParser(description="CI Auth/CSRF Protection Check")
    parser.add_argument(
        "--max-issues",
        type=int,
        default=0,
        help="Maximum number of issues allowed (default: 0)",
    )
    parser.add_argument(
        "--allow-public-issues",
        action="store_true",
        help="Allow issues with public routes (only fail on protected route issues)",
    )
    parser.add_argument(
        "--audit-script",
        default="auth_csrf_audit.py",
        help="Path to the audit script (default: auth_csrf_audit.py)",
    )
    parser.add_argument(
        "--output",
        default="audit_ci_results.json",
        help="Output file for audit results (default: audit_ci_results.json)",
    )

    args = parser.parse_args()

    # Ensure we're in the project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    audit_script = Path(args.audit_script)
    if not audit_script.exists():
        print(f"❌ Audit script not found: {audit_script}")
        return 3

    output_file = Path(args.output)

    # Run the audit script
    print("🔍 Running auth/CSRF dependency audit...")
    try:
        cmd = [sys.executable, str(audit_script), "--output", str(output_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            print(f"❌ Audit script failed with exit code {result.returncode}")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return 3

    except Exception as e:
        print(f"❌ Failed to run audit script: {e}")
        return 3

    # Read and analyze results
    if not output_file.exists():
        print(f"❌ Audit output file not found: {output_file}")
        return 3

    try:
        with open(output_file, "r") as f:
            report = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read audit results: {e}")
        return 3

    # Analyze results
    summary = report.get("summary", {})
    issues = report.get("issues", [])

    total_routes = summary.get("total_routes", 0)
    unprotected_protected = summary.get("unprotected_protected_routes", 0)
    total_issues = summary.get("issues_found", 0)

    print("\n📊 AUDIT RESULTS:")
    print(f"   Total routes analyzed: {total_routes}")
    print(f"   Unprotected protected routes: {unprotected_protected}")
    print(f"   Total issues: {total_issues}")

    # Check for critical issues
    allow_unprotected = os.getenv(
        "ALLOW_UNPROTECTED_ROUTES_FOR_TESTING", "0"
    ).strip().lower() in {"1", "true", "yes", "on"}

    if unprotected_protected > 0:
        if allow_unprotected:
            print(
                f"\n⚠️  WARNING: Found {unprotected_protected} unprotected protected routes!"
            )
            print(
                "   ALLOW_UNPROTECTED_ROUTES_FOR_TESTING=1 is set, so allowing this for testing."
            )
        else:
            print(
                f"\n❌ CRITICAL: Found {unprotected_protected} unprotected protected routes!"
            )
            print(
                "   These routes require authentication but are missing dependency chains."
            )

            # Show some examples
            protected_issues = [
                issue for issue in issues if "Protected route missing" in issue
            ]
            for issue in protected_issues[:5]:  # Show first 5
                print(f"   - {issue}")

            if len(protected_issues) > 5:
                print(f"   ... and {len(protected_issues) - 5} more")

            return 1

    # Check total issues threshold
    if total_issues > args.max_issues:
        print(
            f"\n⚠️  WARNING: Found {total_issues} issues (threshold: {args.max_issues})"
        )

        if not args.allow_public_issues:
            print("   Failing CI due to issue count exceeding threshold.")
            return 2
        else:
            print("   Allowing due to --allow-public-issues flag.")

    # Success
    if total_issues == 0:
        print("\n✅ SUCCESS: No auth/CSRF protection issues found!")
    else:
        print(
            f"\n⚠️  CAUTION: Found {total_issues} issues but within acceptable threshold."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

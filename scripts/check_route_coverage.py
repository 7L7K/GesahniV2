#!/usr/bin/env python3
"""
Route Coverage Checker

This script analyzes route coverage and can be used in CI/CD pipelines
to ensure all canonical routes are tested.

Usage:
    python scripts/check_route_coverage.py [--fail-on-missing] [--verbose]

Options:
    --fail-on-missing: Exit with non-zero code if routes are uncovered
    --verbose: Show detailed coverage report
"""

import sys
import json
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.smoke.test_route_coverage import RouteCoverageAnalyzer


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Check route coverage")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit with non-zero code if routes are uncovered",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed coverage report"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output coverage report as JSON"
    )

    args = parser.parse_args()

    analyzer = RouteCoverageAnalyzer()
    report = analyzer.get_coverage_report()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=== ROUTE COVERAGE REPORT ===")
        print(f"Total routes: {report['total_routes']}")
        print(f"Covered routes: {report['covered_routes']}")
        print(f"Uncovered routes: {report['uncovered_routes']}")
        print(f"Coverage: {report['coverage_percentage']:.1f}%")

        if args.verbose and report["uncovered"]:
            print("\nUncovered routes:")
            for method, path in report["uncovered"]:
                print(f"  {method}: {path}")

            print("\nCovered routes:")
            for method, path in report["covered"]:
                print(f"  {method}: {path}")

    # Exit with failure if requested and routes are uncovered
    if args.fail_on_missing and report["uncovered_routes"] > 0:
        print(f"\n❌ FAIL: {report['uncovered_routes']} routes are uncovered")
        sys.exit(1)
    elif report["uncovered_routes"] == 0:
        print("\n✅ SUCCESS: All routes are covered!")
        sys.exit(0)
    else:
        print(f"\n⚠️  WARNING: {report['uncovered_routes']} routes are uncovered")
        sys.exit(0)


if __name__ == "__main__":
    main()

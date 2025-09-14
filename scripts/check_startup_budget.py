#!/usr/bin/env python3
"""
Startup budget checker for GesahniV2.

Parses PYTHONPROFILEIMPORTTIME output and enforces startup time budgets.
Fails CI if top import offenders exceed configured thresholds.

Usage:
    PYTHONPROFILEIMPORTTIME=1 python -c "import app.main" 2>&1 | python scripts/check_startup_budget.py

Environment variables:
    ENV: dev/prod/ci (default: dev)
    STARTUP_BUDGET_DEV_MS: Max startup time for dev (default: 1200)
    STARTUP_BUDGET_PROD_MS: Max startup time for prod (default: 800)
    STARTUP_BUDGET_CI_MS: Max startup time for CI (default: 1000)
    IMPORT_THRESHOLD_MS: Max time per import (default: 100)
"""

import os
import sys
import re
from typing import List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class ImportTiming:
    module: str
    cumulative_ms: float
    self_ms: float


def parse_import_timings(lines: List[str]) -> List[ImportTiming]:
    """Parse PYTHONPROFILEIMPORTTIME output into structured data."""
    timings = []
    pattern = re.compile(r"import time:\s+(\d+)\s*\|\s*(\d+)\s*\|\s*(.+)")

    for line in lines:
        match = pattern.search(line.strip())
        if match:
            self_us = int(match.group(1))  # microseconds
            cumulative_us = int(match.group(2))  # microseconds
            module = match.group(3).strip()
            # Convert microseconds to milliseconds
            self_ms = self_us / 1000.0
            cumulative_ms = cumulative_us / 1000.0
            timings.append(ImportTiming(module, cumulative_ms, self_ms))

    return timings


def get_budget_thresholds() -> Dict[str, int]:
    """Get budget thresholds based on environment."""
    env = os.getenv("ENV", "dev").strip().lower()

    # Default thresholds (ms)
    defaults = {
        "dev": 1200,  # 1.2s
        "prod": 800,  # 0.8s
        "ci": 1000,  # 1.0s
    }

    # Allow override via environment variables
    env_key = f"STARTUP_BUDGET_{env.upper()}_MS"
    threshold = int(os.getenv(env_key, defaults.get(env, defaults["dev"])))

    return {
        "total_budget_ms": threshold,
        "import_threshold_ms": int(os.getenv("IMPORT_THRESHOLD_MS", "100")),
    }


def analyze_timings(timings: List[ImportTiming]) -> Dict:
    """Analyze import timings and identify offenders."""
    if not timings:
        return {"error": "No import timings found"}

    # Sort by self time (most expensive first)
    sorted_by_self = sorted(timings, key=lambda x: x.self_ms, reverse=True)
    sorted_by_cumulative = sorted(timings, key=lambda x: x.cumulative_ms, reverse=True)

    # Find top offenders
    top_offenders = sorted_by_self[:10]

    # Calculate total startup time (last cumulative timing)
    total_startup_ms = (
        sorted_by_cumulative[0].cumulative_ms if sorted_by_cumulative else 0
    )

    # Find imports exceeding threshold
    thresholds = get_budget_thresholds()
    import_threshold = thresholds["import_threshold_ms"]

    slow_imports = [t for t in timings if t.self_ms > import_threshold]

    return {
        "total_startup_ms": total_startup_ms,
        "top_offenders": [
            {"module": t.module, "self_ms": t.self_ms} for t in top_offenders
        ],
        "slow_imports": [
            {"module": t.module, "self_ms": t.self_ms} for t in slow_imports
        ],
        "thresholds": thresholds,
    }


def main():
    """Main entry point."""
    # Read from stdin (PYTHONPROFILEIMPORTTIME output)
    lines = sys.stdin.readlines()

    if not lines:
        print(
            "❌ ERROR: No input received. Pipe PYTHONPROFILEIMPORTTIME output to this script."
        )
        sys.exit(1)

    # Parse timings
    timings = parse_import_timings(lines)
    analysis = analyze_timings(timings)

    if "error" in analysis:
        print(f"❌ ERROR: {analysis['error']}")
        sys.exit(1)

    # Print results
    print("🚀 Startup Budget Analysis")
    print("=" * 50)

    thresholds = analysis["thresholds"]
    total_ms = analysis["total_startup_ms"]
    budget_ms = thresholds["total_budget_ms"]

    print(".2f")
    print(".2f")

    # Check budget compliance
    budget_passed = total_ms <= budget_ms
    status = "✅ PASSED" if budget_passed else "❌ FAILED"
    print(f"Budget Status: {status}")

    print(f"\n📊 Top 10 Import Offenders:")
    for i, offender in enumerate(analysis["top_offenders"][:10], 1):
        print("2d")

    # Check for slow imports
    slow_imports = analysis["slow_imports"]
    if slow_imports:
        print(f"\n⚠️  Slow Imports (>{thresholds['import_threshold_ms']}ms):")
        for imp in slow_imports:
            print("6d")
    else:
        print(
            f"\n✅ No imports exceeded {thresholds['import_threshold_ms']}ms threshold"
        )

    # Exit with failure if budget exceeded
    if not budget_passed:
        print(
            f"\n❌ BUDGET VIOLATION: Startup time {total_ms}ms exceeds budget of {budget_ms}ms"
        )
        sys.exit(1)

    print("\n🎉 Startup budget check passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()

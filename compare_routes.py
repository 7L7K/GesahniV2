#!/usr/bin/env python3
"""
Compare expected endpoints from tests vs actual routes in FastAPI app.
"""

import re
import json
import pathlib
from app.main import create_app

def get_expected_endpoints():
    """Extract expected endpoints from test files."""
    root = pathlib.Path("tests")
    pattern = re.compile(r'["\']/(?:v1|v0|api)/[^\s"\'\?\)]+')
    expected = set()

    for p in root.rglob("test_*.py"):
        try:
            text = p.read_text(errors="ignore")
            matches = pattern.findall(text)
            expected.update(matches)
        except Exception as e:
            print(f"Error reading {p}: {e}")

    return expected

def get_actual_routes():
    """Get actual routes from FastAPI app."""
    app = create_app()
    routes = set()

    for r in app.routes:
        if hasattr(r, 'path'):
            routes.add(r.path)

    return routes

def main():
    print("🔍 Comparing expected vs actual routes...")

    expected = get_expected_endpoints()
    actual = get_actual_routes()

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)

    print(f"\n📊 Summary:")
    print(f"  Expected endpoints: {len(expected)}")
    print(f"  Actual routes: {len(actual)}")
    print(f"  Missing routes: {len(missing)}")
    print(f"  Extra routes: {len(extra)}")

    if missing:
        print(f"\n❌ MISSING ROUTES ({len(missing)}):")
        for m in missing:
            print(f"  {m}")

    if extra:
        print(f"\n✅ EXTRA ROUTES ({len(extra)}):")
        for e in extra:
            print(f"  {e}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Assert that no FastAPI routes have duplicate (path, method) mappings.

This script fails CI when the same (path, method) is mounted by different callables.
Exits with non-zero status if duplicates are found.
"""
import importlib
import sys
from collections import defaultdict
from typing import Dict, Tuple, Set

# Try common app import locations; adjust if needed
candidates = [
    "app.main:app",
    "app:app",
    "app.server:app",
]
app = None
errors = []
for cand in candidates:
    mod_name, _, attr = cand.partition(":")
    try:
        mod = importlib.import_module(mod_name)
        app = getattr(mod, attr)
        break
    except Exception as e:
        errors.append((cand, repr(e)))
if app is None:
    print("❌ Could not import FastAPI app. Tried:", candidates, file=sys.stderr)
    for cand, err in errors:
        print(f"  - {cand}: {err}", file=sys.stderr)
    sys.exit(2)

# Build mapping of (path, method) -> set of qualified names
route_handlers: Dict[Tuple[str, str], Set[str]] = defaultdict(set)

for route in app.router.routes:
    path = getattr(route, "path", "")
    methods = getattr(route, "methods", set())

    # Skip HEAD and OPTIONS methods as requested
    filtered_methods = methods - {"HEAD", "OPTIONS"}

    if not filtered_methods:
        continue

    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:
        continue

    # Get qualified name for the endpoint
    qualname = (
        f"{endpoint.__module__}.{getattr(endpoint, '__qualname__', endpoint.__name__)}"
    )

    for method in filtered_methods:
        route_handlers[(path, method)].add(qualname)

# Check for duplicates
duplicates_found = False
for (path, method), handlers in sorted(route_handlers.items()):
    if len(handlers) > 1:
        duplicates_found = True
        print(f"❌ DUPLICATE: {method} {path}", file=sys.stderr)
        for handler in sorted(handlers):
            print(f"   → {handler}", file=sys.stderr)
        print(file=sys.stderr)

if duplicates_found:
    print("💥 Route duplicates detected! CI should fail.", file=sys.stderr)
    sys.exit(1)
else:
    print("✅ No route duplicates found.")
    sys.exit(0)

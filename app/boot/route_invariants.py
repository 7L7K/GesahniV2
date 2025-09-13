"""
Route collision detection and invariants.

This module provides runtime assertions to detect route conflicts
and ensure routing invariants are maintained.
"""
from fastapi import FastAPI


def assert_no_route_collisions(app: FastAPI) -> None:
    """
    Assert that no duplicate (path, method) pairs exist in the application routes.

    This function checks all routes in the FastAPI app and raises a RuntimeError
    if any (path, method) combination is registered multiple times, which would
    cause routing conflicts.

    Args:
        app: The FastAPI application instance to check

    Raises:
        RuntimeError: If route collisions are detected, with detailed information
                     about which routes conflict
    """
    seen = {}
    dups = []

    for r in app.routes:
        # Skip routes without methods or path (like Mount objects, etc.)
        if not getattr(r, "methods", None) or not getattr(r, "path", None):
            continue

        for m in r.methods:
            key = (r.path, m.upper())
            route_name = getattr(r, "name", str(r))

            if key in seen:
                dups.append((key, seen[key], route_name))
            else:
                seen[key] = route_name

    if dups:
        lines = [f"{path} {method} -> {existing} vs {new}" for (path, method), existing, new in dups]
        raise RuntimeError("Route collisions detected:\n" + "\n".join(lines))

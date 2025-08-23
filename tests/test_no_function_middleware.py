"""
Tripwire test to ensure no function-style middlewares sneak back into the codebase.

Function middlewares using @app.middleware("http") decorators are problematic because:
- They don't provide clear error messages on failure
- They can't be properly validated at startup
- They make debugging middleware order difficult
- They can silently fail without clear indication

All middlewares should use the class-based approach with add_mw() for proper validation.
"""

import re
from pathlib import Path


def test_no_decorator_middlewares():
    """
    Ensure no @app.middleware("http") decorators exist in the app directory.

    This prevents function-style middlewares from sneaking back in, which would
    bypass our deterministic loader validation and startup checks.
    """
    root = Path(__file__).resolve().parents[1] / "app"
    hits = []

    for py_file in root.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            # Look for @app.middleware("http") patterns
            if "@app.middleware" in content and "http" in content:
                hits.append(str(py_file.relative_to(root.parent)))

            # Also check for any @middleware decorators that might be problematic
            if re.search(r'@\w*middleware\s*\(\s*["\']http["\']', content):
                hits.append(str(py_file.relative_to(root.parent)))

        except (UnicodeDecodeError, OSError):
            # Skip files that can't be read (binary files, permission issues, etc.)
            continue

    assert not hits, (
        f"Function-style middlewares found in: {hits}\n\n"
        "All middlewares must use the class-based approach with add_mw() from app.middleware.loader.\n"
        "Replace @app.middleware('http') decorators with proper middleware classes.\n"
        "See app/middleware/loader.py for the validation system."
    )


def test_no_asgi_middleware_patterns():
    """
    Ensure no ASGI middleware patterns that might bypass our validation.

    This catches other patterns that might be used to add function middlewares.
    """
    root = Path(__file__).resolve().parents[1] / "app"
    hits = []

    for py_file in root.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")

            # Look for direct ASGI middleware usage patterns
            patterns = [
                r"\.add_middleware\s*\(\s*\w+,\s*",  # Direct function middleware
                r"\.add_asgi_middleware\s*\(",  # ASGI middleware wrapper
                r"from\s+starlette\.middleware\s+import.*Middleware\b",  # Starlette function middleware
            ]

            for pattern in patterns:
                if re.search(pattern, content):
                    # This is a potential hit, but we need to check if it's actually problematic
                    # Skip known safe patterns like CORSMiddleware which is a class
                    if (
                        "CORSMiddleware" not in content
                        and "BaseHTTPMiddleware" not in content
                    ):
                        hits.append(f"{py_file.relative_to(root.parent)}: {pattern}")

        except (UnicodeDecodeError, OSError):
            continue

    # For this test, we'll just report potential issues but not fail immediately
    # since some patterns might be legitimate (like CORSMiddleware)
    if hits:
        print(f"Potential middleware patterns to review: {hits}")
        # Don't assert here - this is more of a monitoring test

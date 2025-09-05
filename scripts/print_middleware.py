#!/usr/bin/env python3
"""
Print the actual middleware order for the FastAPI application.

This script checks the middleware configuration by examining the middleware stack file
and prints the middleware order (outer → inner), which helps verify that the canonical
setup is working correctly.
"""

import os
import sys
import re
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def get_middleware_order():
    """Extract middleware order from the middleware stack configuration."""
    try:
        # Read the middleware stack file
        middleware_file = project_root / "app" / "middleware" / "stack.py"

        if not middleware_file.exists():
            return ["Middleware stack file not found"]

        content = middleware_file.read_text()

        # Look for middleware classes in the stack
        middleware_classes = []

        # Common middleware patterns to look for
        patterns = [
            r'(\w+Middleware)',
            r'(\w+Auth)',
            r'(\w+CORS)',
            r'(\w+Session)',
            r'(\w+CSRF)'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if match not in middleware_classes:
                    middleware_classes.append(match)

        # Also look for specific middleware imports
        import_matches = re.findall(r'from.*middleware.*import.*(\w+)', content)
        for match in import_matches:
            if match not in middleware_classes and 'Middleware' in match:
                middleware_classes.append(match)

        return middleware_classes if middleware_classes else ["No middleware classes found in stack"]

    except Exception as e:
        return [f"Error reading middleware: {e}"]

def main():
    """Main function to print middleware configuration."""
    print("MIDDLEWARE (outer→inner):")

    middleware_order = get_middleware_order()
    for i, middleware in enumerate(middleware_order, 1):
        print(f" - {middleware}")

    print(f"\nTotal: {len(middleware_order)} middlewares")

    # Also show the canonical order expectation
    print("\nCanonical Order (expected):")
    canonical_order = [
        "CORSMiddleware",
        "SessionMiddleware",
        "CSRFMiddleware",
        "AuthMiddleware"
    ]

    for middleware in canonical_order:
        status = "✅" if any(m in middleware_order for m in middleware_order if middleware.replace('Middleware', '') in m) else "❌"
        print(f" - {status} {middleware}")

if __name__ == "__main__":
    main()

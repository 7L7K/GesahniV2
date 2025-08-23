"""
Guard test to prevent raw set_cookie usage outside of centralized cookie management.

This test ensures that all Set-Cookie operations go through the centralized
cookie facade in app/cookies.py, preventing inconsistent cookie configuration.
"""

import subprocess
from pathlib import Path

import pytest


def test_no_raw_set_cookie_outside_cookies_module():
    """
    Test that no raw .set_cookie( calls exist outside of allowed files.

    This prevents regressions where developers might bypass the centralized
    cookie management and create inconsistent cookie configurations.
    """
    # Get the project root directory
    project_root = Path(__file__).parent.parent.parent

    # Files that are allowed to contain raw set_cookie calls
    allowed_files = {
        "app/cookies.py",  # The centralized cookie facade
        "app/cookie_config.py",  # Cookie configuration utilities
        "tests/unit/test_cookie_guard.py",  # This test file itself
    }

    # Run ripgrep to find all .set_cookie( calls
    try:
        result = subprocess.run(
            ["rg", "-n", r"\.set_cookie\(", "--type", "py"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse the results
        violations = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            # Parse file:line:content format
            parts = line.split(":", 2)
            if len(parts) >= 2:
                file_path = parts[0]
                line_num = parts[1]
                content = parts[2] if len(parts) > 2 else ""

                # Check if this file is in the allowed list
                if file_path not in allowed_files:
                    violations.append(f"{file_path}:{line_num}: {content.strip()}")

        # If there are violations, fail the test with details
        if violations:
            violation_details = "\n".join(violations)
            pytest.fail(
                f"Found {len(violations)} raw .set_cookie( calls outside allowed files:\n"
                f"Allowed files: {', '.join(allowed_files)}\n\n"
                f"Violations:\n{violation_details}\n\n"
                f"All Set-Cookie operations must go through app/cookies.py facade."
            )

    except subprocess.CalledProcessError as e:
        # ripgrep returns non-zero when no matches found (which is good)
        if e.returncode == 1:
            # No violations found - test passes
            return
        else:
            # Some other error occurred
            pytest.fail(f"ripgrep command failed: {e.stderr}")
    except FileNotFoundError:
        pytest.skip(
            "ripgrep (rg) not found - install with 'brew install ripgrep' or equivalent"
        )


def test_no_raw_set_cookie_in_test_files():
    """
    Test that test files don't contain raw set_cookie calls.

    Tests should use the helper functions from test_helpers.py instead
    of directly calling set_cookie.
    """
    project_root = Path(__file__).parent.parent.parent

    # Run ripgrep to find .set_cookie( calls in test files
    try:
        result = subprocess.run(
            ["rg", "-n", r"\.set_cookie\(", "--type", "py", "--glob", "tests/**/*.py"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse the results
        violations = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            # Parse file:line:content format
            parts = line.split(":", 2)
            if len(parts) >= 2:
                file_path = parts[0]
                line_num = parts[1]
                content = parts[2] if len(parts) > 2 else ""

                # This test file is allowed to contain set_cookie references
                if file_path == "tests/unit/test_cookie_guard.py":
                    continue

                violations.append(f"{file_path}:{line_num}: {content.strip()}")

        # If there are violations, fail the test with details
        if violations:
            violation_details = "\n".join(violations)
            pytest.fail(
                f"Found {len(violations)} raw .set_cookie( calls in test files:\n\n"
                f"Violations:\n{violation_details}\n\n"
                f"Tests should use helper functions from test_helpers.py instead of raw set_cookie calls."
            )

    except subprocess.CalledProcessError as e:
        # ripgrep returns non-zero when no matches found (which is good)
        if e.returncode == 1:
            # No violations found - test passes
            return
        else:
            # Some other error occurred
            pytest.fail(f"ripgrep command failed: {e.stderr}")
    except FileNotFoundError:
        pytest.skip(
            "ripgrep (rg) not found - install with 'brew install ripgrep' or equivalent"
        )


def test_cookies_module_exists():
    """
    Test that the centralized cookies module exists and is importable.

    This ensures the cookie facade is available for tests to use.
    """
    try:
        from app.cookies import clear_auth_cookies, set_auth_cookies

        # If we can import these functions, the test passes
        assert callable(set_auth_cookies)
        assert callable(clear_auth_cookies)
    except ImportError as e:
        pytest.fail(f"Failed to import cookie helper functions: {e}")


def test_test_helpers_exist():
    """
    Test that test helper functions exist for cookie management.

    This ensures tests have access to the proper helper functions.
    """
    try:
        from tests.test_helpers import (
            assert_cookies_cleared,
            assert_cookies_present,
            assert_session_opaque,
            clear_test_auth_cookies,
            set_test_auth_cookies,
        )

        # If we can import these functions, the test passes
        assert callable(set_test_auth_cookies)
        assert callable(clear_test_auth_cookies)
        assert callable(assert_cookies_present)
        assert callable(assert_cookies_cleared)
        assert callable(assert_session_opaque)
    except ImportError as e:
        pytest.fail(f"Failed to import test helper functions: {e}")

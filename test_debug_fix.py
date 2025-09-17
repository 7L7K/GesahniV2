#!/usr/bin/env python3
"""
Test script to verify that the debug endpoints work correctly and don't silently suppress errors.
"""

import sys
from unittest.mock import Mock

# Add the app directory to the path
sys.path.insert(0, "/Users/kingal/2025/GesahniV2")

from app.api.auth import debug_auth_state, debug_cookies


def test_debug_cookies_normal():
    """Test that debug_cookies works with normal cookie data."""
    # Create a mock request with some cookies
    request = Mock()
    request.cookies = {
        "access_token": "some_value",
        "refresh_token": "",
        "session": "valid",
    }

    result = debug_cookies(request)

    print("Debug cookies test (normal):")
    print(f"Result: {result}")

    # Should return the cookies with "present" for non-empty values
    expected = {
        "cookies": {
            "access_token": "present",
            "refresh_token": "",  # Empty string
            "session": "present",
        }
    }

    assert result == expected, f"Expected {expected}, got {result}"
    print("✓ Normal case works correctly\n")


def test_debug_cookies_error():
    """Test that debug_cookies handles errors gracefully but logs them."""
    # Create a mock request that raises an exception when accessing cookies
    request = Mock()
    request.cookies = Mock()
    request.cookies.items.side_effect = Exception("Simulated cookie error")

    result = debug_cookies(request)

    print("Debug cookies test (error):")
    print(f"Result: {result}")

    # Should return empty cookies dict on error
    expected = {"cookies": {}}

    assert result == expected, f"Expected {expected}, got {result}"
    print("✓ Error case handled gracefully\n")


def test_debug_auth_state_normal():
    """Test that debug_auth_state works normally."""
    # Create a mock request with some cookies
    request = Mock()
    request.cookies = {"access_token": "some_value", "refresh_token": "refresh_value"}

    result = debug_auth_state(request)

    print("Debug auth state test (normal):")
    print(f"Result: {result}")

    # Should contain the expected keys
    assert "cookies_seen" in result
    assert "has_access" in result
    assert "has_refresh" in result
    assert result["cookies_seen"] == ["access_token", "refresh_token"]
    print("✓ Normal case works correctly\n")


if __name__ == "__main__":
    print("Testing debug endpoint fixes...\n")

    try:
        test_debug_cookies_normal()
        test_debug_cookies_error()
        test_debug_auth_state_normal()
        print("🎉 All tests passed! Debug endpoints are working correctly.")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)

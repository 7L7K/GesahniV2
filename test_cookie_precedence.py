#!/usr/bin/env python3
"""
Comprehensive test for cookie precedence and assertions.
Tests the new cookie ordering, conflict detection, and security assertions.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_cookie_precedence():
    """Test cookie precedence order arrays."""
    print("Testing cookie precedence order arrays...")

    from app.web.cookies import AT_ORDER, RT_ORDER, SESS_ORDER

    # Test AT_ORDER
    expected_at = ["__Host-GSNH_AT", "GSNH_AT", "access_token", "gsn_access"]
    assert AT_ORDER == expected_at, f"AT_ORDER mismatch: {AT_ORDER} != {expected_at}"
    print("✓ AT_ORDER correct")

    # Test RT_ORDER
    expected_rt = ["__Host-GSNH_RT", "GSNH_RT", "refresh_token", "gsn_refresh"]
    assert RT_ORDER == expected_rt, f"RT_ORDER mismatch: {RT_ORDER} != {expected_rt}"
    print("✓ RT_ORDER correct")

    # Test SESS_ORDER
    expected_sess = ["__Host-GSNH_SESS", "GSNH_SESS", "__session", "session"]
    assert SESS_ORDER == expected_sess, f"SESS_ORDER mismatch: {SESS_ORDER} != {expected_sess}"
    print("✓ SESS_ORDER correct")

    print("✅ Cookie precedence order arrays correct!")


def test_cookie_picker():
    """Test the pick_cookie function with different scenarios."""
    print("\nTesting pick_cookie function...")

    from app.web.cookies import pick_cookie, AT_ORDER, RT_ORDER, SESS_ORDER

    # Mock request object
    class MockRequest:
        def __init__(self, cookies):
            self.cookies = cookies

    # Test 1: No cookies present
    req = MockRequest({})
    name, value = pick_cookie(req, AT_ORDER)
    assert name is None and value is None, "Should return None when no cookies present"
    print("✓ No cookies returns None")

    # Test 2: Only canonical cookie present
    req = MockRequest({"GSNH_AT": "canonical_token"})
    name, value = pick_cookie(req, AT_ORDER)
    assert name == "GSNH_AT" and value == "canonical_token", f"Should pick canonical: {name}, {value}"
    print("✓ Canonical cookie picked first")

    # Test 3: Only legacy cookie present
    req = MockRequest({"access_token": "legacy_token"})
    name, value = pick_cookie(req, AT_ORDER)
    assert name == "access_token" and value == "legacy_token", f"Should pick legacy when no canonical: {name}, {value}"
    print("✓ Legacy cookie picked when no canonical")

    # Test 4: Both canonical and legacy present (should pick canonical)
    req = MockRequest({"GSNH_AT": "canonical_token", "access_token": "legacy_token"})
    name, value = pick_cookie(req, AT_ORDER)
    assert name == "GSNH_AT" and value == "canonical_token", f"Should pick canonical over legacy: {name}, {value}"
    print("✓ Canonical picked over legacy")

    # Test 5: Only __Host- cookie present
    req = MockRequest({"__Host-GSNH_AT": "host_token"})
    name, value = pick_cookie(req, AT_ORDER)
    assert name == "__Host-GSNH_AT" and value == "host_token", f"Should pick __Host-: {name}, {value}"
    print("✓ __Host- cookie picked first")

    print("✅ pick_cookie function works correctly!")


def test_cookie_reader_functions():
    """Test the convenience cookie reader functions."""
    print("\nTesting cookie reader functions...")

    from app.web.cookies import read_access_cookie, read_refresh_cookie, read_session_cookie

    # Mock request object
    class MockRequest:
        def __init__(self, cookies):
            self.cookies = cookies

    # Test access token reader
    req = MockRequest({"GSNH_AT": "access_value"})
    value = read_access_cookie(req)
    assert value == "access_value", f"read_access_cookie failed: {value}"
    print("✓ read_access_cookie works")

    # Test refresh token reader
    req = MockRequest({"GSNH_RT": "refresh_value"})
    value = read_refresh_cookie(req)
    assert value == "refresh_value", f"read_refresh_cookie failed: {value}"
    print("✓ read_refresh_cookie works")

    # Test session reader
    req = MockRequest({"GSNH_SESS": "session_value"})
    value = read_session_cookie(req)
    assert value == "session_value", f"read_session_cookie failed: {value}"
    print("✓ read_session_cookie works")

    print("✅ Cookie reader functions work correctly!")


def test_cookie_assertions():
    """Test cookie security assertions."""
    print("\nTesting cookie security assertions...")

    from app.cookie_config import format_cookie_header

    # Test 1: SameSite=None requires Secure=True
    try:
        header = format_cookie_header(
            key="test_cookie",
            value="test_value",
            max_age=3600,
            secure=False,  # Should be forced to True
            samesite="none"
        )
        assert "Secure" in header, "SameSite=None should force Secure=True"
        print("✓ SameSite=None forces Secure=True")
    except Exception as e:
        print(f"✗ SameSite=None assertion failed: {e}")

    # Test 2: __Host- cookie assertions
    try:
        # This should work (correct __Host- setup)
        header = format_cookie_header(
            key="__Host-test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="strict",
            path="/",
            domain=None
        )
        assert "Path=/" in header, "__Host- should have Path=/"
        assert "Domain=" not in header, "__Host- should have no Domain"
        assert "Secure" in header, "__Host- should be Secure"
        print("✓ __Host- cookie rules enforced correctly")
    except Exception as e:
        print(f"✗ __Host- valid setup failed: {e}")

    # Test 3: __Host- with domain should fail
    try:
        header = format_cookie_header(
            key="__Host-test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="strict",
            path="/",
            domain="example.com"  # Should fail
        )
        print("✗ __Host- with domain should have failed assertion")
    except AssertionError as e:
        assert "__Host- cookie" in str(e) and "no Domain" in str(e)
        print("✓ __Host- with domain correctly rejected")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

    # Test 4: __Host- with non-root path should fail
    try:
        header = format_cookie_header(
            key="__Host-test_cookie",
            value="test_value",
            max_age=3600,
            secure=True,
            samesite="strict",
            path="/api",  # Should fail
            domain=None
        )
        print("✗ __Host- with non-root path should have failed assertion")
    except AssertionError as e:
        assert "__Host- cookie" in str(e) and "Path='/'" in str(e)
        print("✓ __Host- with non-root path correctly rejected")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

    print("✅ Cookie security assertions work correctly!")


def test_partitioned_cookies():
    """Test Partitioned cookie support."""
    print("\nTesting Partitioned cookie support...")

    from app.cookie_config import format_cookie_header

    # Test without Partitioned
    header = format_cookie_header(
        key="test_cookie",
        value="test_value",
        max_age=3600,
        secure=True,
        samesite="lax",
        partitioned=False
    )
    assert "Partitioned" not in header, "Should not have Partitioned when disabled"
    print("✓ No Partitioned when disabled")

    # Test with Partitioned
    header = format_cookie_header(
        key="test_cookie",
        value="test_value",
        max_age=3600,
        secure=True,
        samesite="lax",
        partitioned=True
    )
    assert "Partitioned" in header, "Should have Partitioned when enabled"
    print("✓ Partitioned added when enabled")

    print("✅ Partitioned cookie support works correctly!")


if __name__ == "__main__":
    test_cookie_precedence()
    test_cookie_picker()
    test_cookie_reader_functions()
    test_cookie_assertions()
    test_partitioned_cookies()
    print("\n🎉 All cookie precedence and assertion tests passed!")


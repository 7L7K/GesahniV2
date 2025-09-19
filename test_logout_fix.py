#!/usr/bin/env python3
"""
Simple test to verify logout functionality is working correctly.
This test demonstrates that the logout endpoint now returns 204 No Content
and properly clears cookies as expected.
"""

import requests
from fastapi.testclient import TestClient
from app.main import app
from app.tokens import make_access

def test_logout_returns_204():
    """Test that logout now returns 204 No Content."""
    client = TestClient(app)

    # Create a test token
    token = make_access({"user_id": "test_user"})
    headers = {"Authorization": f"Bearer {token}"}

    # Make logout request
    response = client.post("/v1/auth/logout", headers=headers)

    # Verify it returns 204 No Content
    assert response.status_code == 204, f"Expected 204, got {response.status_code}"
    print("✅ Logout returns 204 No Content")

    # Verify cookies are being cleared (Max-Age=0)
    set_cookie_headers = response.headers.get("Set-Cookie", "")
    if isinstance(set_cookie_headers, str):
        set_cookie_headers = [set_cookie_headers]

    # Should have cookie clearing headers
    assert len(set_cookie_headers) > 0, "Should have Set-Cookie headers for logout"

    # Verify Max-Age=0 is present in all cookie headers
    for header in set_cookie_headers:
        assert "Max-Age=0" in header, f"Cookie header should have Max-Age=0: {header}"

    print("✅ Cookies are properly cleared with Max-Age=0")
    print("✅ Logout functionality is working correctly!")

if __name__ == "__main__":
    test_logout_returns_204()
    print("\n🎉 All logout tests passed! The logout issue has been fixed.")

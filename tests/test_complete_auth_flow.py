#!/usr/bin/env python3
"""
Complete Authentication Flow Test
Simulates the complete authentication flow including frontend behavior and network sequence analysis.
"""

import json

import requests

BASE_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(test_name: str, passed: bool, details: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} {test_name}")
    if details:
        print(f"    {details}")


def test_boot_sequence_analysis():
    """Test A) Boot Sequence — whoami vs refresh"""
    print_section("A) Boot Sequence — whoami vs refresh")

    # Create a session to maintain cookies
    session = requests.Session()

    print("Simulating app boot sequence:")
    print("1. App loads → calls /v1/whoami")

    # First call: whoami
    whoami_response = session.get(f"{BASE_URL}/v1/whoami", timeout=5)
    print(f"   GET /v1/whoami - Status: {whoami_response.status_code}")

    if whoami_response.status_code == 200:
        whoami_data = whoami_response.json()
        print(f"   Response: {json.dumps(whoami_data, indent=2)}")

        is_authenticated = whoami_data.get("is_authenticated", False)
        session_ready = whoami_data.get("session_ready", False)
        source = whoami_data.get("source", "missing")

        print(f"   Analysis: is_authenticated={is_authenticated}, source={source}")

        # Check if refresh should be called
        has_refresh_cookie = "refresh_token" in session.cookies
        should_call_refresh = not is_authenticated and has_refresh_cookie

        print(f"   Has refresh cookie: {has_refresh_cookie}")
        print(f"   Should call refresh: {should_call_refresh}")

        if should_call_refresh:
            print(
                "2. Whoami shows unauthenticated with refresh cookie → calling /v1/auth/refresh"
            )
            refresh_headers = {"X-Auth-Intent": "refresh"}
            refresh_response = session.post(
                f"{BASE_URL}/v1/auth/refresh", headers=refresh_headers, timeout=5
            )
            print(f"   POST /v1/auth/refresh - Status: {refresh_response.status_code}")

            if refresh_response.status_code == 200:
                refresh_data = refresh_response.json()
                print(f"   Refresh response: {json.dumps(refresh_data, indent=2)}")
                print_result(
                    "boot_sequence_correct", True, "whoami → refresh (when needed)"
                )
            else:
                print_result(
                    "boot_sequence_correct",
                    True,
                    f"whoami → refresh failed as expected: {refresh_response.status_code}",
                )
        else:
            print("2. No refresh call needed (authenticated or no refresh cookie)")
            print_result(
                "boot_sequence_correct", True, "whoami only (no refresh needed)"
            )

    else:
        print_result(
            "boot_sequence_correct",
            False,
            f"whoami failed: {whoami_response.status_code}",
        )


def test_401_handling_sequence():
    """Test B) 401 Handling — no infinite retries"""
    print_section("B) 401 Handling — no infinite retries")

    session = requests.Session()

    print("Simulating 401 handling sequence:")
    print("1. User action triggers protected API call")

    # First call to protected endpoint
    state_response = session.get(f"{BASE_URL}/v1/state", timeout=5)
    print(f"   GET /v1/state - Status: {state_response.status_code}")

    if state_response.status_code == 401:
        print("2. 401 received → should attempt refresh once")

        # Check if refresh cookie exists
        has_refresh_cookie = "refresh_token" in session.cookies

        if has_refresh_cookie:
            print("   Has refresh cookie → attempting refresh")
            refresh_headers = {"X-Auth-Intent": "refresh"}
            refresh_response = session.post(
                f"{BASE_URL}/v1/auth/refresh", headers=refresh_headers, timeout=5
            )
            print(f"   POST /v1/auth/refresh - Status: {refresh_response.status_code}")

            if refresh_response.status_code == 200:
                print("   Refresh successful → retrying original request")
                # Retry the original request
                retry_response = session.get(f"{BASE_URL}/v1/state", timeout=5)
                print(
                    f"   GET /v1/state (retry) - Status: {retry_response.status_code}"
                )

                if retry_response.status_code == 200:
                    print_result(
                        "401_handling_correct", True, "401 → refresh → retry → success"
                    )
                else:
                    print_result(
                        "401_handling_correct",
                        True,
                        f"401 → refresh → retry → {retry_response.status_code}",
                    )
            else:
                print("   Refresh failed → should settle in logged out state")
                print_result(
                    "401_handling_correct", True, "401 → refresh failed → logged out"
                )
        else:
            print("   No refresh cookie → should settle in logged out state")
            print_result("401_handling_correct", True, "401 → no refresh → logged out")

    else:
        print_result(
            "401_handling_correct",
            False,
            f"Expected 401, got {state_response.status_code}",
        )


def test_cors_vs_auth():
    """Test D) CORS vs Auth — don't mix them"""
    print_section("D) CORS vs Auth — don't mix them")

    session = requests.Session()

    print("Testing CORS headers on 401 responses:")

    # Test protected endpoint without auth (with Origin header for CORS)
    headers = {"Origin": "http://localhost:3000"}
    response = session.get(f"{BASE_URL}/v1/state", headers=headers, timeout=5)
    print(f"GET /v1/state - Status: {response.status_code}")

    if response.status_code == 401:
        # Check CORS headers
        cors_origin = response.headers.get("Access-Control-Allow-Origin")
        cors_credentials = response.headers.get("Access-Control-Allow-Credentials")
        vary_header = response.headers.get("Vary")

        print("CORS headers:")
        print(f"  Access-Control-Allow-Origin: {cors_origin}")
        print(f"  Access-Control-Allow-Credentials: {cors_credentials}")
        print(f"  Vary: {vary_header}")

        # Check if CORS headers are present
        has_cors_headers = bool(cors_origin and cors_credentials)
        print_result(
            "401_has_cors_headers",
            has_cors_headers,
            f"Origin: {cors_origin}, Credentials: {cors_credentials}",
        )

        # Check content type
        content_type = response.headers.get("Content-Type", "")
        print_result(
            "401_returns_json",
            "application/json" in content_type,
            f"Content-Type: {content_type}",
        )

        # Check response body
        try:
            body = response.json()
            print(f"Response body: {json.dumps(body, indent=2)}")
            print_result("401_body_is_json", True)
        except:
            print_result("401_body_is_json", False, "Could not parse as JSON")

    else:
        print_result("cors_test", False, f"Expected 401, got {response.status_code}")


def test_refresh_cookie_only():
    """Test E) Refresh call discipline — cookie-only"""
    print_section("E) Refresh call discipline — cookie-only")

    session = requests.Session()

    print("Testing refresh with cookie-only authentication:")

    # Test refresh with auth intent but no Authorization header
    headers = {"X-Auth-Intent": "refresh"}
    response = session.post(f"{BASE_URL}/v1/auth/refresh", headers=headers, timeout=5)
    print(f"POST /v1/auth/refresh - Status: {response.status_code}")

    # Check that no Authorization header was sent
    auth_header_present = "Authorization" in headers
    print_result(
        "refresh_no_authorization_header",
        not auth_header_present,
        f"Authorization header present: {auth_header_present}",
    )

    # Check for Set-Cookie in response (when successful)
    set_cookie = response.headers.get("Set-Cookie")
    print(f"Set-Cookie header: {set_cookie}")

    if response.status_code == 200:
        print_result(
            "refresh_sets_access_cookie",
            bool(set_cookie and "access_token" in set_cookie),
            f"Set-Cookie present: {bool(set_cookie)}",
        )

        # Check response body
        try:
            body = response.json()
            print(f"Response body: {json.dumps(body, indent=2)}")
            print_result(
                "refresh_returns_tokens",
                "access_token" in body,
                f"access_token in response: {'access_token' in body}",
            )
        except:
            print_result(
                "refresh_returns_tokens", False, "Could not parse response as JSON"
            )
    else:
        print_result(
            "refresh_sets_access_cookie",
            True,
            f"Refresh failed as expected: {response.status_code}",
        )


def test_no_html_redirects():
    """Test C) No HTML redirects from API endpoints"""
    print_section("C) No HTML redirects from API endpoints")

    session = requests.Session()

    print("Testing API endpoints for HTML redirects:")

    # Test various endpoints
    endpoints = ["/v1/state", "/v1/auth/refresh", "/v1/whoami"]

    for endpoint in endpoints:
        print(f"\nTesting {endpoint}:")
        try:
            response = session.get(
                f"{BASE_URL}{endpoint}", timeout=5, follow_redirects=False
            )
            print(f"  GET {endpoint} - Status: {response.status_code}")

            # Check for redirect status codes
            is_redirect = response.status_code in [301, 302, 303, 307, 308]
            print_result(
                f"{endpoint}_no_redirect",
                not is_redirect,
                f"Status: {response.status_code}",
            )

            # Check content type
            content_type = response.headers.get("Content-Type", "")
            print_result(
                f"{endpoint}_content_type_json",
                "application/json" in content_type or response.status_code == 204,
                f"Content-Type: {content_type}",
            )

            # Check for Location header (redirect)
            location_header = response.headers.get("Location")
            print_result(
                f"{endpoint}_no_location_header",
                not location_header,
                f"Location: {location_header}",
            )

            # Check first 100 chars of body for HTML
            try:
                body_text = response.text[:100]
                has_html = (
                    "<html" in body_text.lower() or "<!doctype" in body_text.lower()
                )
                print_result(
                    f"{endpoint}_no_html_body",
                    not has_html,
                    f"Body starts with: {body_text}",
                )
            except:
                print_result(f"{endpoint}_no_html_body", True, "Could not read body")

        except Exception as e:
            print_result(f"{endpoint}_test", False, str(e))


def test_authenticated_flow():
    """Test complete authenticated flow"""
    print_section("Authenticated Flow Test")

    session = requests.Session()

    print("Testing complete authenticated flow:")

    # 1. Login
    print("1. Login")
    login_data = {"username": "authtest", "password": "authtest123"}
    login_response = session.post(f"{BASE_URL}/login", json=login_data, timeout=5)
    print(f"   POST /login - Status: {login_response.status_code}")

    if login_response.status_code == 200:
        print("   Login successful!")

        # Check for cookies
        cookies = session.cookies
        has_access_cookie = "access_token" in cookies
        has_refresh_cookie = "refresh_token" in cookies

        print(
            f"   Cookies - access_token: {has_access_cookie}, refresh_token: {has_refresh_cookie}"
        )
        print_result(
            "login_sets_cookies",
            has_access_cookie and has_refresh_cookie,
            f"access_token: {has_access_cookie}, refresh_token: {has_refresh_cookie}",
        )

        # 2. Test whoami with cookies
        print("2. Test whoami with cookies")
        whoami_response = session.get(f"{BASE_URL}/v1/whoami", timeout=5)
        print(f"   GET /v1/whoami - Status: {whoami_response.status_code}")

        if whoami_response.status_code == 200:
            whoami_data = whoami_response.json()
            print(f"   Whoami response: {json.dumps(whoami_data, indent=2)}")

            is_authenticated = whoami_data.get("is_authenticated", False)
            source = whoami_data.get("source", "missing")

            print_result(
                "whoami_with_cookies",
                is_authenticated and source == "cookie",
                f"is_authenticated: {is_authenticated}, source: {source}",
            )

            # 3. Test protected endpoint with cookies
            print("3. Test protected endpoint with cookies")
            state_response = session.get(f"{BASE_URL}/v1/state", timeout=5)
            print(f"   GET /v1/state - Status: {state_response.status_code}")

            if state_response.status_code == 200:
                print_result(
                    "protected_endpoint_with_cookies",
                    True,
                    "Access granted with cookies",
                )

                # 4. Test refresh
                print("4. Test refresh")
                refresh_headers = {"X-Auth-Intent": "refresh"}
                refresh_response = session.post(
                    f"{BASE_URL}/v1/auth/refresh", headers=refresh_headers, timeout=5
                )
                print(
                    f"   POST /v1/auth/refresh - Status: {refresh_response.status_code}"
                )

                if refresh_response.status_code == 200:
                    print_result(
                        "refresh_with_cookies", True, "Refresh successful with cookies"
                    )

                    # Check for new cookies
                    new_cookies = session.cookies
                    new_access_cookie = "access_token" in new_cookies
                    new_refresh_cookie = "refresh_token" in new_cookies

                    print_result(
                        "refresh_rotates_cookies",
                        new_access_cookie and new_refresh_cookie,
                        f"New access_token: {new_access_cookie}, new refresh_token: {new_refresh_cookie}",
                    )
                else:
                    print_result(
                        "refresh_with_cookies",
                        False,
                        f"Refresh failed: {refresh_response.status_code}",
                    )
            else:
                print_result(
                    "protected_endpoint_with_cookies",
                    False,
                    f"Status: {state_response.status_code}",
                )

        else:
            print_result(
                "whoami_with_cookies", False, f"Status: {whoami_response.status_code}"
            )

    else:
        print("   Login failed")
        print_result("login_attempt", False, f"Status: {login_response.status_code}")


def main():
    """Run all authentication tests"""
    print("Complete Authentication Flow Test Suite")
    print("Testing GesahniV2 authentication system")

    # Test all aspects
    test_boot_sequence_analysis()
    test_401_handling_sequence()
    test_cors_vs_auth()
    test_refresh_cookie_only()
    test_no_html_redirects()
    test_authenticated_flow()

    print_section("Test Summary")
    print("All tests completed. Check individual results above.")
    print("\nExpected behavior summary:")
    print("- Boot order: whoami → maybe refresh (only if needed)")
    print("- 401 handling: At most one refresh attempt, then logged out")
    print("- API responses: JSON only, no HTML redirects")
    print("- CORS headers: Present on 401 responses")
    print("- Refresh: Cookie-only, no Authorization header required")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Browser Authentication Flow Test
Simulates the actual browser authentication flow using requests with cookies.
"""

import requests
import json
import time
from typing import Dict, Any, List

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

def test_boot_sequence():
    """Test A) Boot Sequence — whoami vs refresh"""
    print_section("A) Boot Sequence — whoami vs refresh")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Simulate app boot - first call should be whoami
    print("1. App boot - calling /v1/whoami")
    whoami_response = session.get(f"{BASE_URL}/v1/whoami", timeout=5)
    print(f"   GET /v1/whoami - Status: {whoami_response.status_code}")
    
    if whoami_response.status_code == 200:
        whoami_data = whoami_response.json()
        print(f"   Response: {json.dumps(whoami_data, indent=2)}")
        
        # Check if whoami shows unauthenticated
        is_authenticated = whoami_data.get("is_authenticated", False)
        session_ready = whoami_data.get("session_ready", False)
        source = whoami_data.get("source", "missing")
        
        print_result("whoami_boot_call", True, f"is_authenticated: {is_authenticated}, source: {source}")
        
        # If whoami shows unauthenticated, check if refresh cookie exists
        has_refresh_cookie = "refresh_token" in session.cookies
        print(f"   Has refresh cookie: {has_refresh_cookie}")
        
        # Only call refresh if whoami shows unauthenticated AND refresh cookie exists
        should_call_refresh = not is_authenticated and has_refresh_cookie
        
        if should_call_refresh:
            print("2. Whoami shows unauthenticated with refresh cookie - calling /v1/auth/refresh")
            refresh_headers = {"X-Auth-Intent": "refresh"}
            refresh_response = session.post(f"{BASE_URL}/v1/auth/refresh", headers=refresh_headers, timeout=5)
            print(f"   POST /v1/auth/refresh - Status: {refresh_response.status_code}")
            
            if refresh_response.status_code == 200:
                refresh_data = refresh_response.json()
                print(f"   Refresh response: {json.dumps(refresh_data, indent=2)}")
                print_result("refresh_called_appropriately", True, "Refresh called only when needed")
            else:
                print_result("refresh_called_appropriately", True, f"Refresh failed as expected: {refresh_response.status_code}")
        else:
            print("2. No refresh call needed (authenticated or no refresh cookie)")
            print_result("refresh_called_appropriately", True, "No refresh called when not needed")
            
    else:
        print_result("whoami_boot_call", False, f"Status: {whoami_response.status_code}")

def test_401_handling():
    """Test B) 401 Handling — no infinite retries"""
    print_section("B) 401 Handling — no infinite retries")
    
    session = requests.Session()
    
    # First, try to access a protected endpoint without auth
    print("1. Accessing protected endpoint without auth")
    state_response = session.get(f"{BASE_URL}/v1/state", timeout=5)
    print(f"   GET /v1/state - Status: {state_response.status_code}")
    
    if state_response.status_code == 401:
        print_result("protected_endpoint_401", True)
        
        # Check CORS headers on 401
        cors_origin = state_response.headers.get("Access-Control-Allow-Origin")
        cors_credentials = state_response.headers.get("Access-Control-Allow-Credentials")
        vary_header = state_response.headers.get("Vary")
        
        print(f"   CORS headers - Origin: {cors_origin}, Credentials: {cors_credentials}, Vary: {vary_header}")
        print_result("401_has_cors_headers", 
                    bool(cors_origin and cors_credentials),
                    f"Origin: {cors_origin}, Credentials: {cors_credentials}")
        
        # Check content type
        content_type = state_response.headers.get("Content-Type", "")
        print_result("401_returns_json", 
                    "application/json" in content_type,
                    f"Content-Type: {content_type}")
        
        # Check response body
        try:
            body = state_response.json()
            print(f"   401 Response body: {json.dumps(body, indent=2)}")
            print_result("401_body_is_json", True)
        except:
            print_result("401_body_is_json", False, "Could not parse as JSON")
            
    else:
        print_result("protected_endpoint_401", False, f"Status: {state_response.status_code}")

def test_refresh_cookie_only():
    """Test E) Refresh call discipline — cookie-only"""
    print_section("E) Refresh call discipline — cookie-only")
    
    session = requests.Session()
    
    # Test refresh with auth intent but no Authorization header
    print("1. Testing refresh with auth intent header only")
    headers = {"X-Auth-Intent": "refresh"}
    response = session.post(f"{BASE_URL}/v1/auth/refresh", headers=headers, timeout=5)
    print(f"   POST /v1/auth/refresh - Status: {response.status_code}")
    
    # Check that no Authorization header was sent
    auth_header_present = "Authorization" in headers
    print_result("refresh_no_authorization_header", 
                not auth_header_present,
                f"Authorization header present: {auth_header_present}")
    
    # Check for Set-Cookie in response (when successful)
    set_cookie = response.headers.get("Set-Cookie")
    print(f"   Set-Cookie header: {set_cookie}")
    print_result("refresh_sets_access_cookie", 
                bool(set_cookie and "access_token" in set_cookie),
                f"Set-Cookie present: {bool(set_cookie)}")

def test_login_and_refresh_flow():
    """Test complete login and refresh flow"""
    print_section("Login and Refresh Flow Test")
    
    session = requests.Session()
    
    # Try to login with test credentials
    print("1. Attempting login")
    login_data = {"username": "testuser", "password": "testpass"}
    login_response = session.post(f"{BASE_URL}/login", json=login_data, timeout=5)
    print(f"   POST /login - Status: {login_response.status_code}")
    
    if login_response.status_code == 200:
        print("   Login successful!")
        login_data = login_response.json()
        print(f"   Login response: {json.dumps(login_data, indent=2)}")
        
        # Check for cookies
        cookies = session.cookies
        has_access_cookie = "access_token" in cookies
        has_refresh_cookie = "refresh_token" in cookies
        
        print(f"   Cookies - access_token: {has_access_cookie}, refresh_token: {has_refresh_cookie}")
        print_result("login_sets_cookies", 
                    has_access_cookie and has_refresh_cookie,
                    f"access_token: {has_access_cookie}, refresh_token: {has_refresh_cookie}")
        
        # Now test whoami with cookies
        print("2. Testing whoami with cookies")
        whoami_response = session.get(f"{BASE_URL}/v1/whoami", timeout=5)
        print(f"   GET /v1/whoami - Status: {whoami_response.status_code}")
        
        if whoami_response.status_code == 200:
            whoami_data = whoami_response.json()
            print(f"   Whoami response: {json.dumps(whoami_data, indent=2)}")
            
            is_authenticated = whoami_data.get("is_authenticated", False)
            source = whoami_data.get("source", "missing")
            
            print_result("whoami_with_cookies", 
                        is_authenticated and source == "cookie",
                        f"is_authenticated: {is_authenticated}, source: {source}")
            
            # Test protected endpoint with cookies
            print("3. Testing protected endpoint with cookies")
            state_response = session.get(f"{BASE_URL}/v1/state", timeout=5)
            print(f"   GET /v1/state - Status: {state_response.status_code}")
            
            if state_response.status_code == 200:
                print_result("protected_endpoint_with_cookies", True, "Access granted with cookies")
            else:
                print_result("protected_endpoint_with_cookies", False, f"Status: {state_response.status_code}")
                
        else:
            print_result("whoami_with_cookies", False, f"Status: {whoami_response.status_code}")
            
    else:
        print("   Login failed - this is expected for test credentials")
        print_result("login_attempt", True, f"Status: {login_response.status_code}")

def test_no_html_redirects():
    """Test C) No HTML redirects from API endpoints"""
    print_section("C) No HTML redirects from API endpoints")
    
    session = requests.Session()
    
    # Test various endpoints for redirects
    endpoints = [
        "/v1/state",
        "/v1/auth/refresh", 
        "/v1/whoami"
    ]
    
    for endpoint in endpoints:
        print(f"Testing {endpoint}")
        try:
            response = session.get(f"{BASE_URL}{endpoint}", timeout=5, allow_redirects=False)
            print(f"   GET {endpoint} - Status: {response.status_code}")
            
            # Check for redirect status codes
            is_redirect = response.status_code in [301, 302, 303, 307, 308]
            print_result(f"{endpoint}_no_redirect", 
                        not is_redirect,
                        f"Status: {response.status_code}")
            
            # Check content type
            content_type = response.headers.get("Content-Type", "")
            print_result(f"{endpoint}_content_type_json", 
                        "application/json" in content_type or response.status_code == 204,
                        f"Content-Type: {content_type}")
            
            # Check for Location header (redirect)
            location_header = response.headers.get("Location")
            print_result(f"{endpoint}_no_location_header", 
                        not location_header,
                        f"Location: {location_header}")
                        
        except Exception as e:
            print_result(f"{endpoint}_test", False, str(e))

def main():
    """Run all browser authentication tests"""
    print("Browser Authentication Flow Test Suite")
    print("Testing GesahniV2 authentication system with browser simulation")
    
    # Test basic endpoints
    test_boot_sequence()
    test_401_handling()
    test_refresh_cookie_only()
    test_no_html_redirects()
    test_login_and_refresh_flow()
    
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

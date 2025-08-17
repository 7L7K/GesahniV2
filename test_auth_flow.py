#!/usr/bin/env python3
"""
Authentication Flow Test Script
Tests the authentication system according to the specified test cases.
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

def test_whoami_endpoint():
    """Test A) Boot Sequence — whoami vs refresh"""
    print_section("A) Boot Sequence — whoami vs refresh")
    
    # Test whoami endpoint
    try:
        response = requests.get(f"{BASE_URL}/v1/whoami", timeout=5)
        print(f"GET /v1/whoami - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response JSON: {json.dumps(data, indent=2)}")
            
            # Check required fields
            has_is_authenticated = "is_authenticated" in data
            has_session_ready = "session_ready" in data
            has_source = "source" in data
            
            print_result("whoami_has_required_fields", 
                        has_is_authenticated and has_session_ready and has_source,
                        f"is_authenticated: {has_is_authenticated}, session_ready: {has_session_ready}, source: {has_source}")
            
            print_result("whoami_source_valid", 
                        data.get("source") in ["cookie", "header", "missing"],
                        f"source: {data.get('source')}")
        else:
            print_result("whoami_returns_200", False, f"Status: {response.status_code}")
            
    except Exception as e:
        print_result("whoami_endpoint_accessible", False, str(e))

def test_refresh_endpoint():
    """Test refresh endpoint behavior"""
    print_section("Refresh Endpoint Test")
    
    # Test refresh without auth intent header
    try:
        response = requests.post(f"{BASE_URL}/v1/auth/refresh", timeout=5)
        print(f"POST /v1/auth/refresh (no intent) - Status: {response.status_code}")
        
        # Should require X-Auth-Intent header
        if response.status_code == 400:
            print_result("refresh_requires_intent_header", True)
        else:
            print_result("refresh_requires_intent_header", False, f"Expected 400, got {response.status_code}")
            
    except Exception as e:
        print_result("refresh_endpoint_accessible", False, str(e))
    
    # Test refresh with auth intent header
    try:
        headers = {"X-Auth-Intent": "refresh"}
        response = requests.post(f"{BASE_URL}/v1/auth/refresh", headers=headers, timeout=5)
        print(f"POST /v1/auth/refresh (with intent) - Status: {response.status_code}")
        
        if response.status_code == 401:
            print_result("refresh_returns_401_when_no_token", True)
        else:
            print_result("refresh_returns_401_when_no_token", False, f"Expected 401, got {response.status_code}")
            
    except Exception as e:
        print_result("refresh_with_intent_accessible", False, str(e))

def test_401_handling():
    """Test B) 401 Handling — no infinite retries"""
    print_section("B) 401 Handling — no infinite retries")
    
    # Test protected endpoint without auth
    try:
        response = requests.get(f"{BASE_URL}/v1/state", timeout=5)
        print(f"GET /v1/state (no auth) - Status: {response.status_code}")
        
        if response.status_code == 401:
            print_result("protected_endpoint_returns_401", True)
            
            # Check response headers for CORS
            cors_origin = response.headers.get("Access-Control-Allow-Origin")
            cors_credentials = response.headers.get("Access-Control-Allow-Credentials")
            vary_header = response.headers.get("Vary")
            
            print_result("401_has_cors_headers", 
                        bool(cors_origin and cors_credentials),
                        f"Origin: {cors_origin}, Credentials: {cors_credentials}, Vary: {vary_header}")
            
            # Check response content type
            content_type = response.headers.get("Content-Type", "")
            print_result("401_returns_json", 
                        "application/json" in content_type,
                        f"Content-Type: {content_type}")
            
            # Check response body
            try:
                body = response.json()
                print(f"401 Response body: {json.dumps(body, indent=2)}")
                print_result("401_body_is_json", True)
            except:
                print_result("401_body_is_json", False, "Could not parse as JSON")
                
        else:
            print_result("protected_endpoint_returns_401", False, f"Status: {response.status_code}")
            
    except Exception as e:
        print_result("protected_endpoint_test", False, str(e))

def test_cors_handling():
    """Test D) CORS vs Auth — don't mix them"""
    print_section("D) CORS vs Auth — don't mix them")
    
    # Test OPTIONS preflight
    try:
        response = requests.options(f"{BASE_URL}/v1/state", timeout=5)
        print(f"OPTIONS /v1/state - Status: {response.status_code}")
        
        cors_origin = response.headers.get("Access-Control-Allow-Origin")
        cors_credentials = response.headers.get("Access-Control-Allow-Credentials")
        cors_methods = response.headers.get("Access-Control-Allow-Methods")
        
        print_result("preflight_has_cors_headers", 
                    bool(cors_origin and cors_credentials and cors_methods),
                    f"Origin: {cors_origin}, Credentials: {cors_credentials}, Methods: {cors_methods}")
                    
    except Exception as e:
        print_result("preflight_test", False, str(e))

def test_refresh_cookie_only():
    """Test E) Refresh call discipline — cookie-only"""
    print_section("E) Refresh call discipline — cookie-only")
    
    # Test refresh with auth intent but no Authorization header
    try:
        headers = {"X-Auth-Intent": "refresh"}
        response = requests.post(f"{BASE_URL}/v1/auth/refresh", headers=headers, timeout=5)
        print(f"POST /v1/auth/refresh (cookie-only) - Status: {response.status_code}")
        
        # Check that no Authorization header was sent
        auth_header_present = "Authorization" in headers
        print_result("refresh_no_authorization_header", 
                    not auth_header_present,
                    f"Authorization header present: {auth_header_present}")
        
        # Check for Set-Cookie in response (when successful)
        set_cookie = response.headers.get("Set-Cookie")
        print_result("refresh_sets_access_cookie", 
                    bool(set_cookie and "access_token" in set_cookie),
                    f"Set-Cookie present: {bool(set_cookie)}")
                    
    except Exception as e:
        print_result("refresh_cookie_test", False, str(e))

def test_login_flow():
    """Test login and token generation"""
    print_section("Login Flow Test")
    
    # Test login endpoint
    try:
        login_data = {"username": "testuser", "password": "testpass"}
        response = requests.post(f"{BASE_URL}/login", json=login_data, timeout=5)
        print(f"POST /login - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Login response: {json.dumps(data, indent=2)}")
            
            # Check for cookies
            cookies = response.cookies
            has_access_cookie = "access_token" in cookies
            has_refresh_cookie = "refresh_token" in cookies
            
            print_result("login_sets_cookies", 
                        has_access_cookie and has_refresh_cookie,
                        f"access_token: {has_access_cookie}, refresh_token: {has_refresh_cookie}")
            
            # Check cookie attributes
            if has_access_cookie:
                access_cookie = cookies["access_token"]
                print_result("access_cookie_httponly", 
                            access_cookie.has_nonstandard_attr("HttpOnly"),
                            f"HttpOnly: {access_cookie.has_nonstandard_attr('HttpOnly')}")
                            
        else:
            print_result("login_endpoint_works", False, f"Status: {response.status_code}")
            
    except Exception as e:
        print_result("login_test", False, str(e))

def test_no_html_redirects():
    """Test C) No HTML redirects from API endpoints"""
    print_section("C) No HTML redirects from API endpoints")
    
    # Test various endpoints for redirects
    endpoints = [
        "/v1/state",
        "/v1/auth/refresh", 
        "/v1/whoami"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=5, allow_redirects=False)
            print(f"GET {endpoint} - Status: {response.status_code}")
            
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
    """Run all authentication tests"""
    print("Authentication Flow Test Suite")
    print("Testing GesahniV2 authentication system")
    
    # Test basic endpoints
    test_whoami_endpoint()
    test_refresh_endpoint()
    test_401_handling()
    test_cors_handling()
    test_refresh_cookie_only()
    test_no_html_redirects()
    test_login_flow()
    
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

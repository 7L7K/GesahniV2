#!/usr/bin/env python3
"""
Test script to verify cookie configuration matches requirements:
- Names: access_token, refresh_token, __session (optional)
- Attributes per cookie:
  - Path=/
  - HttpOnly
  - SameSite=Lax
  - No Secure (for dev HTTP)
  - No Domain (host-only)
  - Max-Age (access ~15m, refresh ~30d)
  - Priority=High
- Delete flow uses identical attrs + Max-Age=0
"""

import os
import sys
import requests
import json
from datetime import datetime

# Configuration
API_URL = "http://localhost:8000"
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass123"

def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result with consistent formatting."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} {test_name}")
    if details:
        print(f"   {details}")
    print()

def test_cookie_attributes(cookie_header: str, cookie_name: str, expected_max_age: int) -> bool:
    """Test that a cookie has the required attributes."""
    if not cookie_header:
        return False
    
    # Parse cookie attributes
    parts = cookie_header.split("; ")
    cookie_dict = {}
    
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            cookie_dict[key.lower()] = value
        else:
            cookie_dict[part.lower()] = "true"
    
    # Check required attributes
    checks = [
        ("path", "/"),
        ("httponly", "true"),
        ("samesite", "lax"),
        ("priority", "high"),
    ]
    
    for attr, expected_value in checks:
        if attr not in cookie_dict:
            print(f"   Missing attribute: {attr}")
            return False
        if cookie_dict[attr].lower() != expected_value.lower():
            print(f"   Wrong {attr}: expected {expected_value}, got {cookie_dict[attr]}")
            return False
    
    # Check Max-Age
    if "max-age" not in cookie_dict:
        print(f"   Missing Max-Age attribute")
        return False
    
    try:
        max_age = int(cookie_dict["max-age"])
        # Allow some tolerance for the expected values
        if cookie_name == "access_token":
            expected_range = (800, 1000)  # ~15 minutes (900 seconds)
        elif cookie_name == "refresh_token":
            expected_range = (2592000 - 3600, 2592000 + 3600)  # ~30 days with 1 hour tolerance
        else:
            expected_range = (expected_max_age - 60, expected_max_age + 60)
        
        if not (expected_range[0] <= max_age <= expected_range[1]):
            print(f"   Wrong Max-Age: expected ~{expected_max_age}s, got {max_age}s")
            return False
    except ValueError:
        print(f"   Invalid Max-Age value: {cookie_dict['max-age']}")
        return False
    
    # Check that Secure is NOT present (for dev HTTP)
    if "secure" in cookie_dict:
        print(f"   Secure attribute should not be present in dev HTTP mode")
        return False
    
    # Check that Domain is NOT present (host-only)
    if "domain" in cookie_dict:
        print(f"   Domain attribute should not be present (host-only cookies)")
        return False
    
    return True

def main():
    print("🧪 Testing Cookie Configuration")
    print("=" * 50)
    
    # Test 1: Login and check cookie attributes
    print("1. Testing login cookie attributes...")
    
    try:
        # Attempt login
        login_data = {
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        }
        
        response = requests.post(f"{API_URL}/v1/login", json=login_data)
        
        if response.status_code == 200:
            print_result("login_success", True, f"Status: {response.status_code}")
            
            # Check Set-Cookie headers
            set_cookie_headers = response.headers.get("set-cookie", "")
            if not set_cookie_headers:
                print_result("login_sets_cookies", False, "No Set-Cookie headers found")
                return
            
            # Parse multiple cookies
            cookies = {}
            for cookie_header in set_cookie_headers.split(", "):
                if "=" in cookie_header:
                    name = cookie_header.split("=")[0]
                    cookies[name] = cookie_header
            
            # Test required cookies
            required_cookies = ["access_token", "refresh_token"]
            
            for cookie_name in required_cookies:
                if cookie_name in cookies:
                    if cookie_name == "access_token":
                        expected_max_age = 900  # 15 minutes
                    else:  # refresh_token
                        expected_max_age = 2592000  # 30 days
                    
                    passed = test_cookie_attributes(cookies[cookie_name], cookie_name, expected_max_age)
                    print_result(f"cookie_{cookie_name}_attributes", passed, f"Cookie: {cookie_name}")
                else:
                    print_result(f"cookie_{cookie_name}_present", False, f"Missing cookie: {cookie_name}")
            
            # Test optional __session cookie
            if "__session" in cookies:
                passed = test_cookie_attributes(cookies["__session"], "__session", 900)  # Same as access token
                print_result("cookie___session_attributes", passed, "Optional __session cookie")
            else:
                print_result("cookie___session_optional", True, "__session cookie not present (optional)")
            
            # Store cookies for logout test
            session_cookies = {}
            for cookie_header in set_cookie_headers.split(", "):
                if "=" in cookie_header:
                    name = cookie_header.split("=")[0]
                    value = cookie_header.split("=")[1].split(";")[0]
                    session_cookies[name] = value
            
        else:
            print_result("login_success", False, f"Status: {response.status_code}, Response: {response.text}")
            return
            
    except Exception as e:
        print_result("login_request", False, f"Exception: {e}")
        return
    
    # Test 2: Logout and check cookie clearing
    print("\n2. Testing logout cookie clearing...")
    
    try:
        # Attempt logout with cookies
        logout_response = requests.post(f"{API_URL}/v1/auth/logout", cookies=session_cookies)
        
        if logout_response.status_code == 204:
            print_result("logout_success", True, f"Status: {logout_response.status_code}")
            
            # Check Set-Cookie headers for clearing
            set_cookie_headers = logout_response.headers.get("set-cookie", "")
            if not set_cookie_headers:
                print_result("logout_clears_cookies", False, "No Set-Cookie headers found")
                return
            
            # Parse multiple cookies
            cookies = {}
            for cookie_header in set_cookie_headers.split(", "):
                if "=" in cookie_header:
                    name = cookie_header.split("=")[0]
                    cookies[name] = cookie_header
            
            # Test that cookies are cleared with Max-Age=0
            required_cookies = ["access_token", "refresh_token", "__session"]
            
            for cookie_name in required_cookies:
                if cookie_name in cookies:
                    # Check that Max-Age=0 for clearing
                    if "max-age=0" in cookies[cookie_name].lower():
                        print_result(f"logout_clears_{cookie_name}", True, f"Cookie {cookie_name} cleared with Max-Age=0")
                    else:
                        print_result(f"logout_clears_{cookie_name}", False, f"Cookie {cookie_name} not cleared properly")
                else:
                    print_result(f"logout_clears_{cookie_name}", False, f"Missing clear header for {cookie_name}")
            
        else:
            print_result("logout_success", False, f"Status: {logout_response.status_code}, Response: {logout_response.text}")
            
    except Exception as e:
        print_result("logout_request", False, f"Exception: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Cookie Configuration Test Summary")
    print("Expected configuration:")
    print("   - Names: access_token, refresh_token, __session (optional)")
    print("   - Attributes: Path=/, HttpOnly, SameSite=Lax, No Secure, No Domain")
    print("   - Max-Age: access ~15m (900s), refresh ~30d (2592000s)")
    print("   - Priority=High for auth cookies")
    print("   - Delete flow: identical attrs + Max-Age=0")

if __name__ == "__main__":
    main()

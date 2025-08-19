#!/usr/bin/env python3
"""
Debug script to check TTL values in login endpoint
"""

import os
import requests

# Load environment variables from env.localhost
if os.path.exists("env.localhost"):
    with open("env.localhost", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

print("Environment variable values:")
print(f"JWT_EXPIRE_MINUTES: {os.getenv('JWT_EXPIRE_MINUTES', 'NOT_SET')}")
print(f"JWT_REFRESH_EXPIRE_MINUTES: {os.getenv('JWT_REFRESH_EXPIRE_MINUTES', 'NOT_SET')}")
print(f"JWT_REFRESH_TTL_SECONDS: {os.getenv('JWT_REFRESH_TTL_SECONDS', 'NOT_SET')}")
print(f"JWT_ACCESS_TTL_SECONDS: {os.getenv('JWT_ACCESS_TTL_SECONDS', 'NOT_SET')}")

# Test the TTL functions
from app.cookie_config import get_token_ttls
access_ttl, refresh_ttl = get_token_ttls()
print(f"\nCookie config TTLs:")
print(f"access_ttl: {access_ttl} seconds ({access_ttl/60:.1f} minutes)")
print(f"refresh_ttl: {refresh_ttl} seconds ({refresh_ttl/86400:.1f} days)")

# Test the auth TTL function
from app.api.auth import _get_refresh_ttl_seconds
refresh_ttl_auth = _get_refresh_ttl_seconds()
print(f"\nAuth refresh TTL: {refresh_ttl_auth} seconds ({refresh_ttl_auth/86400:.1f} days)")

# Test login and check actual cookie values
print(f"\nTesting login endpoint...")
response = requests.post("http://localhost:8000/v1/auth/login?username=testuser")
print(f"Login status: {response.status_code}")

set_cookie_headers = response.headers.get("set-cookie", "")
if isinstance(set_cookie_headers, str):
    set_cookie_headers = [set_cookie_headers]

print(f"\nActual Set-Cookie headers:")
for header in set_cookie_headers:
    if "access_token=" in header:
        print(f"access_token: {header}")
        if "Max-Age=" in header:
            max_age_start = header.find("Max-Age=") + 8
            max_age_end = header.find(";", max_age_start)
            if max_age_end == -1:
                max_age_end = len(header)
            max_age = header[max_age_start:max_age_end]
            print(f"  Max-Age value: {max_age}")
    elif "refresh_token=" in header:
        print(f"refresh_token: {header}")
        if "Max-Age=" in header:
            max_age_start = header.find("Max-Age=") + 8
            max_age_end = header.find(";", max_age_start)
            if max_age_end == -1:
                max_age_end = len(header)
            max_age = header[max_age_start:max_age_end]
            print(f"  Max-Age value: {max_age}")

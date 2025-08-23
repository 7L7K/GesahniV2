#!/usr/bin/env python3
"""
Test script to check environment variable values
"""

import os

# Load environment variables from env.localhost
if os.path.exists("env.localhost"):
    with open("env.localhost") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

print("Environment variable values:")
print(f"JWT_EXPIRE_MINUTES: {os.getenv('JWT_EXPIRE_MINUTES', 'NOT_SET')}")
print(f"JWT_REFRESH_EXPIRE_MINUTES: {os.getenv('JWT_REFRESH_EXPIRE_MINUTES', 'NOT_SET')}")
print(f"JWT_REFRESH_TTL_SECONDS: {os.getenv('JWT_REFRESH_TTL_SECONDS', 'NOT_SET')}")

# Test the TTL functions
from app.cookie_config import get_token_ttls

access_ttl, refresh_ttl = get_token_ttls()
print("\nCookie config TTLs:")
print(f"access_ttl: {access_ttl} seconds ({access_ttl/60:.1f} minutes)")
print(f"refresh_ttl: {refresh_ttl} seconds ({refresh_ttl/86400:.1f} days)")

# Test the auth TTL function
from app.api.auth import _get_refresh_ttl_seconds

refresh_ttl_auth = _get_refresh_ttl_seconds()
print(f"\nAuth refresh TTL: {refresh_ttl_auth} seconds ({refresh_ttl_auth/86400:.1f} days)")

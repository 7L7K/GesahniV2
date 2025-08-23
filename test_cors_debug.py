#!/usr/bin/env python3

import os

from app.env_utils import load_env

# Load environment
load_env()

# Check CORS configuration
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

print(f"Raw CORS_ALLOW_ORIGINS: {repr(_cors_origins)}")
print(f"Parsed origins: {origins}")

# Check if multiple origins are configured
if len(origins) > 1:
    print(f"Multiple origins detected. Using first: {origins[0]}")
    origins = [origins[0]]

if not origins:
    print("No origins configured. Defaulting to http://localhost:3000")
    origins = ["http://localhost:3000"]

print(f"Final CORS origins: {origins}")

# Test if localhost:3000 is in the allowed origins
test_origin = "http://localhost:3000"
if test_origin in origins:
    print(f"✓ {test_origin} is allowed")
else:
    print(f"✗ {test_origin} is NOT allowed")
    print(f"Allowed origins: {origins}")

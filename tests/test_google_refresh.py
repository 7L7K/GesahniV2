#!/usr/bin/env python3
import os
from fastapi.testclient import TestClient
from app.main import app

# Set test environment
os.environ['TEST_MODE'] = '1'
os.environ['JWT_OPTIONAL_IN_TESTS'] = '1'

client = TestClient(app)

# Test what happens when we try to refresh the expired token
print("🧪 Testing Google Token Refresh Logic...")

# First, let's see what the current token data looks like
print("\n1. Current token status:")
response = client.get("/v1/google/status")
if response.status_code == 200:
    data = response.json()
    print(f"   Connected: {data.get('connected')}")
    print(f"   Expires at: {data.get('expires_at')}")
    print(f"   Scopes: {data.get('scopes', [])}")
    
    # Check if token is expired
    import time
    current_time = int(time.time())
    expires_at = data.get('expires_at', 0)
    if expires_at < current_time:
        print(f"   ❌ Token expired {current_time - expires_at} seconds ago")
        
        # Check STALE_BUFFER logic
        STALE_BUFFER = 300  # 5 minutes
        time_diff = expires_at - current_time  # This will be negative
        print(f"   Time diff: {time_diff} seconds")
        print(f"   STALE_BUFFER: {STALE_BUFFER} seconds")
        print(f"   Should refresh: {time_diff < STALE_BUFFER}")
    else:
        print(f"   ✅ Token valid for {expires_at - current_time} seconds")
else:
    print(f"   ❌ Failed to get status: {response.status_code}")

print("\n🎯 Analysis:")
print("   - The token is EXPIRED (August 14, 2025)")
print("   - The STALE_BUFFER logic should trigger refresh")
print("   - But refresh likely fails due to expired refresh token")
print("   - Google status endpoint may not be handling this properly")

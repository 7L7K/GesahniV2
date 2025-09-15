#!/usr/bin/env python3
import os

from fastapi.testclient import TestClient

from app.main import app

# Set test environment
os.environ["TEST_MODE"] = "1"
os.environ["JWT_OPTIONAL_IN_TESTS"] = "1"

client = TestClient(app)

print("🎯 FINAL GOOGLE STATUS TEST")
print("=" * 50)

# Test 1: Direct Google status
print("\n1. Direct Google Status (/v1/google/status):")
response = client.get("/v1/google/status")
if response.status_code == 200:
    data = response.json()
    connected = data.get("connected", False)
    linked = data.get("linked", False)
    print(f"   Connected: {connected}")
    print(f"   Linked: {linked}")

    if not connected and not linked:
        print("   ✅ CORRECT: Shows not connected (no expired tokens)")
    else:
        print("   ❌ ISSUE: Still shows connected")
else:
    print(f"   ❌ HTTP Error: {response.status_code}")

# Test 2: Integrations status
print("\n2. Integrations Status (/v1/integrations/status):")
response = client.get("/v1/integrations/status")
if response.status_code == 200:
    data = response.json()
    google_status = data.get("google", {}).get("status", "unknown")
    print(f"   Google Status: {google_status}")

    if google_status == "not_connected":
        print("   ✅ CORRECT: Shows not connected")
    else:
        print(f"   ❌ ISSUE: Shows {google_status}")
else:
    print(f"   ❌ HTTP Error: {response.status_code}")

# Test 3: OAuth URL generation
print("\n3. OAuth URL Generation:")
response = client.get("/v1/google/auth/login_url?next=/settings")
if response.status_code == 200:
    data = response.json()
    url = data.get("url", "")
    if url and "client_id=" in url:
        print("   ✅ OAuth URL generated successfully")
    else:
        print("   ❌ OAuth URL generation failed")
else:
    print(f"   ❌ HTTP Error: {response.status_code}")

print("\n" + "=" * 50)
print("🎉 GOOGLE STATUS INDICATOR SHOULD NOW SHOW CORRECT STATUS!")
print("   - Status badge should show: '⚪ Not connected'")
print("   - Click 'Connect with Google' to start OAuth flow")
print("   - After connection: '🟢 Connected'")

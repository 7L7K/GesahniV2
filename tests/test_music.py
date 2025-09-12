#!/usr/bin/env python3
"""Test script to verify music endpoints work correctly."""

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.music_http import router as music_router

# Set test environment
os.environ["TEST_MODE"] = "1"
os.environ["JWT_OPTIONAL_IN_TESTS"] = "1"

# Create test app
app = FastAPI()
app.include_router(music_router, prefix="/v1")

# Create test client
client = TestClient(app)

print("Testing music endpoints...")

# Test the /v1/state endpoint
print("\n1. Testing /v1/state endpoint:")
response = client.get("/v1/state")
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

# Test other music endpoints
print("\n2. Testing /v1/music/devices endpoint:")
response = client.get("/v1/music/devices")
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

# Test POST endpoints
print("\n3. Testing POST /v1/music endpoint:")
response = client.post("/v1/music", json={"command": "play"})
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

print("\nTest completed.")

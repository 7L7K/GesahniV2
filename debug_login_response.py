#!/usr/bin/env python3
"""Debug the login response."""

import requests

# Call the login endpoint
url = "http://localhost:8000/v1/spotify/login?user_id=test_user"
cookies = {"auth_token": "dummy_jwt_token"}

print("Making request to:", url)
response = requests.get(url, cookies=cookies)

print(f"Status: {response.status_code}")
print(f"Content-Type: {response.headers.get('content-type')}")

try:
    data = response.json()
    print(f"JSON data: {data}")
    print(f"Keys in data: {list(data.keys())}")

    # Check different possible key names
    for key in ['auth_url', 'authorize_url', 'url']:
        value = data.get(key)
        print(f"data.get('{key}') = {value}")

except Exception as e:
    print(f"JSON parsing error: {e}")
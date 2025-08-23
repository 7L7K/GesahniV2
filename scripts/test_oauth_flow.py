#!/usr/bin/env python3
"""Quick smoke test: exercise /v1/google/auth/login_url -> /v1/google/auth/callback
This uses FastAPI TestClient and patches the exchange_code to return a stubbed creds object.
"""
import os

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-1")
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

# Import the app after setting env
from app.main import app


class _StubCreds:
    def __init__(self):
        self.token = "access-token-stub"
        self.refresh_token = "refresh-token-stub"
        # id_token contains email/sub claims; callback decodes without verification
        self.id_token = jwt.encode(
            {"email": "smoke@example.com", "sub": "smoke-sub"}, "x", algorithm="HS256"
        )
        self.scopes = ["openid", "email", "profile"]
        import datetime

        self.expiry = datetime.datetime.utcnow()
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "cli-id")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "cli-secret")


client = TestClient(app)

print("Requesting login_url...")
r = client.get("/v1/google/auth/login_url?next=/")
print("login_url status", r.status_code)
print("resp json keys:", r.json().keys())

# Extract state cookie
state_cookie = client.cookies.get("g_state")
print("g_state cookie present?", bool(state_cookie))
print("g_state cookie value:", state_cookie)

# Now patch exchange_code to return stub creds and call callback
with patch(
    "app.integrations.google.oauth.exchange_code",
    lambda code, state, verify_state=False: _StubCreds(),
):
    print("\nCalling callback with patched exchange_code...")
    # Use the state value from cookie (the endpoint expects state param)
    params = {"code": "fake-code", "state": state_cookie}
    r2 = client.get("/v1/google/auth/callback", params=params, allow_redirects=False)
    print("callback status", r2.status_code)

    # Show all response headers
    print("\n=== CALLBACK RESPONSE HEADERS ===")
    for header, value in r2.headers.items():
        print(f"{header}: {value}")

    # Show cookies that were set
    print("\n=== COOKIES SET BY CALLBACK ===")
    for cookie_name, cookie_value in client.cookies.items():
        print(f"{cookie_name}: {cookie_value}")

    if r2.is_redirect:
        print("\nredirect location:", r2.headers.get("location"))
    else:
        print("\ncallback body:", r2.text)

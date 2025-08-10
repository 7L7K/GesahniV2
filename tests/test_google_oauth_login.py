import os
import sys
import tempfile
from importlib import import_module
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _StubCreds:
    def __init__(self):
        # Minimal fields used by creds_to_record
        self.token = "at"
        self.refresh_token = "rt"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.client_id = "cid"
        self.client_secret = "csec"
        self.scopes = ["openid", "email", "profile"]
        # id_token with unverified claims that include email
        # We don't need a valid signature for get_unverified_claims
        import base64, json

        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({"email": "guser@example.com"}).encode()).rstrip(b"=")
        self.id_token = (header + b"." + payload + b".").decode()


def _app(monkeypatch):
    # Ensure fresh modules
    for m in [
        "app.integrations.google.db",
        "app.integrations.google.config",
        "app.integrations.google.oauth",
        "app.integrations.google.routes",
    ]:
        sys.modules.pop(m, None)

    # Temp dbs
    users_fd, users_path = tempfile.mkstemp()
    os.close(users_fd)
    google_db_fd, google_db_path = tempfile.mkstemp()
    os.close(google_db_fd)

    monkeypatch.setenv("USERS_DB", users_path)
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("APP_URL", "http://app.example")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "y")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://testserver/google/oauth/callback")
    monkeypatch.setenv("GOOGLE_OAUTH_DB_URL", f"sqlite:///{google_db_path}")

    # Import modules after env
    oauth = import_module("app.integrations.google.oauth")
    # Stub out the exchange to avoid network before importing routes (so the imported
    # symbol in routes refers to our stub)
    monkeypatch.setattr(oauth, "exchange_code", lambda code, state: _StubCreds())
    routes = import_module("app.integrations.google.routes")
    # Ensure DB tables exist for the test database
    gdb = import_module("app.integrations.google.db")
    gdb.init_db()

    app = FastAPI()
    app.include_router(routes.router, prefix="/google")
    client = TestClient(app)
    return client


def test_google_login_flow(monkeypatch):
    client = _app(monkeypatch)

    # 1) Start login: we get an auth URL with a signed state
    r1 = client.get("/google/auth/login_url", params={"next": "/"})
    assert r1.status_code == 200
    auth_url = r1.json()["auth_url"]
    assert "https://accounts.google.com" in auth_url

    # Extract the state parameter to feed back into callback
    parsed = urlparse(auth_url)
    q = parse_qs(parsed.query)
    state = q.get("state", [None])[0]
    assert state

    # 2) Callback: should redirect to APP_URL with app tokens
    r2 = client.get("/google/oauth/callback", params={"code": "dummy", "state": state}, allow_redirects=False)
    assert r2.status_code in (302, 307)
    location = r2.headers.get("Location")
    assert location and location.startswith("http://app.example/login?")

    # Verify tokens present and structurally valid
    q2 = parse_qs(urlparse(location).query)
    at = q2.get("access_token", [None])[0]
    rt = q2.get("refresh_token", [None])[0]
    assert at and rt



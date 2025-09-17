import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure required settings exist before importing router dependencies.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://user:pass@localhost/testdb"
)
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.integrations.google.routes import router  # noqa: E402


def test_connect_sets_state_and_next_cookies(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid-test")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI", "https://example.com/v1/google/auth/callback"
    )

    app = FastAPI()
    app.include_router(router, prefix="/v1/google")

    with TestClient(app) as client:
        resp = client.get("/v1/google/integration/connect?next=/settings")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload.get("authorize_url", "").startswith(
            "https://accounts.google.com/o/oauth2/v2/auth"
        )
        assert payload.get("state")

        # Cookies should include signed state and sanitized next target for Google provider.
        assert resp.cookies.get("g_state")
        assert resp.cookies.get("g_next") == "/settings"

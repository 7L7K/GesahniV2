import sys
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.deps.user import get_current_user_id


def _client(tmp_path, monkeypatch):
    db_path = tmp_path / "google.sqlite3"
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("GOOGLE_OAUTH_DB_URL", f"sqlite:///{db_path}")

    # reload modules to pick up env vars
    for mod in list(sys.modules):
        if mod.startswith("app.integrations.google"):
            del sys.modules[mod]

    from importlib import import_module

    routes = import_module("app.integrations.google.routes")

    app = FastAPI()
    app.include_router(routes.router, prefix="/google")
    client = TestClient(app)
    client.__enter__()
    return client, routes


def _override(user_id: str):
    def _inner(request: Request = None):
        if request is not None:
            request.state.user_id = user_id
        return user_id

    return _inner


def test_oauth_flow_two_users(tmp_path, monkeypatch):
    client, routes = _client(tmp_path, monkeypatch)

    # stub out Google OAuth interactions
    monkeypatch.setattr(routes, "build_auth_url", lambda uid: (f"http://auth/{uid}", f"state-{uid}"))
    monkeypatch.setattr(routes, "exchange_code", lambda code, state: code)

    def fake_creds_to_record(code: str):
        return {
            "access_token": f"access-{code}",
            "refresh_token": f"refresh-{code}",
            "token_uri": "uri",
            "client_id": "cid",
            "client_secret": "secret",
            "scopes": "s1 s2",
            "expiry": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(routes, "creds_to_record", fake_creds_to_record)

    # user1 flow
    client.app.dependency_overrides[get_current_user_id] = _override("user1")
    r1 = client.get("/google/auth/url")
    assert r1.json()["auth_url"] == "http://auth/user1"
    cb1 = client.get("/google/oauth/callback", params={"code": "c1", "state": "state-user1"})
    assert cb1.status_code == 200
    s1 = client.get("/google/status")
    assert s1.json()["linked"] is True

    # user2 flow
    client.app.dependency_overrides[get_current_user_id] = _override("user2")
    r2 = client.get("/google/auth/url")
    assert r2.json()["auth_url"] == "http://auth/user2"
    cb2 = client.get("/google/oauth/callback", params={"code": "c2", "state": "state-user2"})
    assert cb2.status_code == 200
    s2 = client.get("/google/status")
    assert s2.json()["linked"] is True

    with routes.SessionLocal() as s:
        row1 = s.get(routes.GoogleToken, "user1")
        row2 = s.get(routes.GoogleToken, "user2")
        assert row1.access_token == "access-c1"
        assert row2.access_token == "access-c2"

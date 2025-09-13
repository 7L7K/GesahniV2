import sys

import psycopg2
from fastapi import FastAPI
from fastapi.testclient import TestClient


def get_db_connection():
    """Get connection to test PostgreSQL database."""
    return psycopg2.connect("postgresql://app:app_pw@localhost:5432/gesahni_test")


def _client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    # Use long TTL for testing to prevent expiry mid-test
    sys.modules.pop("app.auth", None)
    from importlib import import_module

    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)

    # Clean up any existing test users
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM auth.users WHERE username = %s", ("alice",))
        conn.commit()
    conn.close()

    client.post("/register", json={"username": "alice", "password": "wonderland"})
    return client


def test_login_unknown_hash_returns_401(monkeypatch):
    client = _client(monkeypatch)
    # Corrupt the stored hash with an unknown scheme
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE auth.users SET password_hash=%s WHERE username=%s",
            ("md5$deadbeef", "alice"),
        )
        conn.commit()
    conn.close()
    r = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert r.status_code == 401


def test_password_strength_enforced_when_env_set(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s")
    monkeypatch.setenv("PASSWORD_STRENGTH", "1")
    sys.modules.pop("app.auth", None)
    from importlib import import_module

    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)

    # Clean up any existing test users
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM auth.users WHERE username = %s", ("bob",))
        conn.commit()
    conn.close()

    client = TestClient(app)
    # Too weak under PASSWORD_STRENGTH=1
    r = client.post("/register", json={"username": "bob", "password": "secret"})
    assert r.status_code == 400


def test_refresh_uses_cookie_when_body_missing(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert r.status_code == 200
    # Cookies persisted in client are used by /refresh without body
    r2 = client.post("/refresh")
    assert r2.status_code == 200


def test_register_username_taken(monkeypatch):
    client = _client(monkeypatch)
    # Clean up any existing test users with different password
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM auth.users WHERE username = %s", ("alice",))
        conn.commit()
    conn.close()

    # First register alice
    client.post("/register", json={"username": "alice", "password": "wonderland"})

    # Try to register again with different password - should fail
    r = client.post("/register", json={"username": "alice", "password": "wonderland2"})
    assert r.status_code == 400


def test_logout_invalid_token_returns_204(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/logout", headers={"Authorization": "Bearer notatoken"})
    assert r.status_code == 204

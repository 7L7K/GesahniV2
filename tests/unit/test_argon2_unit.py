from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app


def _client(tmp_path=None):
    if tmp_path:
        os.environ["USERS_DB"] = str(tmp_path / "users.db")
    return TestClient(app)


def test_argon2_register_and_login(tmp_path):
    c = _client(tmp_path)
    r = c.post("/v1/auth/register_pw", json={"username": "bob", "password": "secret12"})
    assert r.status_code == 200
    # Correct password
    r2 = c.post("/v1/auth/login_pw", json={"username": "bob", "password": "secret12"})
    assert r2.status_code == 200
    # Wrong password
    r3 = c.post("/v1/auth/login_pw", json={"username": "bob", "password": "WRONG"})
    assert r3.status_code == 401



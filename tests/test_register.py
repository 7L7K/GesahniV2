import os
import sqlite3
import tempfile
import importlib
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.deps.user import get_current_user_id


def test_register_and_duplicate():
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    os.environ["USERS_DB"] = db_path

    from app import auth

    importlib.reload(auth)

    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)

    resp = client.post("/register", json={"username": "alice", "password": "secret"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    conn = sqlite3.connect(db_path)
    stored = conn.execute(
        "SELECT password_hash FROM users WHERE username=?", ("alice",)
    ).fetchone()[0]
    assert stored != "secret"
    assert auth.pwd_context.verify("secret", stored)

    resp2 = client.post("/register", json={"username": "alice", "password": "x"})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "username_taken"


def test_register_sets_user_id():
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    os.environ["USERS_DB"] = db_path

    from app import auth

    importlib.reload(auth)

    app = FastAPI()
    app.include_router(auth.router)

    captured: dict[str, str] = {}

    def fake_user_id(request: Request) -> str:
        request.state.user_id = "testuser"
        captured["user_id"] = request.state.user_id
        return "testuser"

    app.dependency_overrides[get_current_user_id] = fake_user_id

    client = TestClient(app)
    resp = client.post("/register", json={"username": "bob", "password": "secret"})
    assert resp.status_code == 200
    assert captured["user_id"] == "testuser"

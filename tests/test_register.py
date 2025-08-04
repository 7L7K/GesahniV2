import os
import sqlite3
import tempfile
import importlib
from fastapi import FastAPI
from fastapi.testclient import TestClient


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

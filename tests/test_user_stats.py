from hashlib import sha256
from importlib import import_module, reload

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient


def test_login_and_me(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("USER_DB", str(db_path))
    monkeypatch.setenv("USERS_DB", str(db_path))
    monkeypatch.setenv("JWT_SECRET", "secret")

    import app.user_store as user_store

    reload(user_store)
    from app.user_store import user_store as store

    import sys

    sys.modules.pop("app.auth", None)
    auth = import_module("app.auth")

    def _anon_user_id(request: Request) -> str:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            return sha256(auth_header.encode("utf-8")).hexdigest()[:32]
        return "local"

    async def get_current_user_id(request: Request) -> str:
        uid = _anon_user_id(request)
        request.state.user_id = uid
        return uid

    app = FastAPI()

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        uid = _anon_user_id(request)
        await store.ensure_user(uid)
        await store.increment_request(uid)
        return await call_next(request)

    app.include_router(auth.router)

    @app.get("/me")
    async def me(user_id: str = Depends(get_current_user_id)):
        stats = await store.get_stats(user_id)
        return {"user_id": user_id, **stats}

    app.dependency_overrides[auth.get_current_user_id] = get_current_user_id

    client = TestClient(app)
    headers = {"Authorization": "token123"}

    client.post(
        "/register",
        json={"username": "alice", "password": "wonderland"},
        headers=headers,
    )

    r1 = client.post(
        "/login",
        json={"username": "alice", "password": "wonderland"},
        headers=headers,
    )
    data1 = r1.json()
    assert "token" in data1
    stats1 = data1["stats"]
    assert stats1["login_count"] == 1
    assert stats1["request_count"] == 2
    last1 = stats1["last_login"]

    r2 = client.get("/me", headers=headers)
    data2 = r2.json()
    assert data2["login_count"] == 1
    assert data2["request_count"] == 3
    assert data2["last_login"] == last1

    r3 = client.post(
        "/login",
        json={"username": "alice", "password": "wonderland"},
        headers=headers,
    )
    data3 = r3.json()["stats"]
    assert data3["login_count"] == 2
    assert data3["request_count"] == 4
    assert data3["last_login"] != last1

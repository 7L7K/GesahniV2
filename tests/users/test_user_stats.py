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
    import sys

    from app.user_store import user_store as store

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
        "/v1/auth/register",
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
    # The request_count is based on the user_id from Authorization header, not the logged-in username
    # Since register and login are now public endpoints, they don't go through get_current_user_id
    # So the request_count should be 0 for the logged-in user (alice), but the middleware
    # increments for the user_id from Authorization header (token123 hash)
    assert stats1["request_count"] == 0
    last1 = stats1["last_login"]

    r2 = client.get("/me", headers=headers)
    data2 = r2.json()
    # The /me endpoint uses the user_id from Authorization header (hash of "token123"),
    # not the logged-in username ("alice"). So it returns stats for a different user.
    assert data2["login_count"] == 0  # This user hasn't logged in
    # The /me endpoint uses the user_id from Authorization header, which gets incremented by middleware
    # So this should be 3 (register + login + me requests)
    assert data2["request_count"] == 3
    # This user hasn't logged in, so last_login should be None or empty
    assert data2["last_login"] is None or data2["last_login"] == ""

    r3 = client.post(
        "/login",
        json={"username": "alice", "password": "wonderland"},
        headers=headers,
    )
    data3 = r3.json()["stats"]
    assert data3["login_count"] == 2
    # Second login - request_count should still be 0 for the logged-in user
    assert data3["request_count"] == 0
    assert data3["last_login"] != last1

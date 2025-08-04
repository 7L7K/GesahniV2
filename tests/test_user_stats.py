from hashlib import sha256
from importlib import reload

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient


def test_login_and_me(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_DB", str(tmp_path / "users.db"))
    import app.user_store as user_store
    reload(user_store)

    def _anon_user_id(request: Request) -> str:
        auth = request.headers.get("Authorization")
        if auth:
            return sha256(auth.encode("utf-8")).hexdigest()[:32]
        return "local"

    async def get_current_user_id(request: Request) -> str:
        uid = _anon_user_id(request)
        request.state.user_id = uid
        return uid

    app = FastAPI()

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        uid = _anon_user_id(request)
        await user_store.user_store.ensure_user(uid)
        await user_store.user_store.increment_request(uid)
        return await call_next(request)

    @app.post("/login")
    async def login(user_id: str = Depends(get_current_user_id)):
        await user_store.user_store.increment_login(user_id)
        stats = await user_store.user_store.get_stats(user_id)
        return {"user_id": user_id, **stats}

    @app.get("/me")
    async def me(user_id: str = Depends(get_current_user_id)):
        stats = await user_store.user_store.get_stats(user_id)
        return {"user_id": user_id, **stats}

    client = TestClient(app)
    headers = {"Authorization": "token123"}

    r1 = client.post("/login", headers=headers)
    data1 = r1.json()
    assert data1["login_count"] == 1
    assert data1["request_count"] == 1
    last1 = data1["last_login"]

    r2 = client.get("/me", headers=headers)
    data2 = r2.json()
    assert data2["login_count"] == 1
    assert data2["request_count"] == 2
    assert data2["last_login"] == last1

    r3 = client.post("/login", headers=headers)
    data3 = r3.json()
    assert data3["login_count"] == 2
    assert data3["request_count"] == 3
    assert data3["last_login"] != last1

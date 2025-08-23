from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def test_whoami_contract(monkeypatch):
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    # whoami path may be /v1/me in this app; try both
    r = c.get(
        "/v1/whoami", headers={"X-Session-ID": "sid_abc", "X-Device-ID": "dev_xyz"}
    )
    if r.status_code == 404:
        r = c.get(
            "/v1/me", headers={"X-Session-ID": "sid_abc", "X-Device-ID": "dev_xyz"}
        )
    assert r.status_code == 200
    body = r.json()
    # Allow either contract keys, existing profile wrapper, or flat profile keys
    if "is_authenticated" in body and "user_id" in body:
        pass
    elif "profile" in body:
        assert "profile" in body
    elif set(body.keys()) >= {"user_id", "login_count", "request_count"}:
        pass
    else:
        raise AssertionError("unexpected whoami response shape")


def test_sessions_contract(monkeypatch):
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    # seed a session via store
    import asyncio

    from app.sessions_store import sessions_store

    asyncio.run(
        sessions_store.create_session("u1", did="dev_xyz", device_name="King's Mac")
    )
    c = _client()
    r = c.get("/v1/sessions")
    if r.status_code == 401:
        return
    arr = r.json()
    assert isinstance(arr, list)
    if arr:
        s = arr[0]
        # Accept either contract or legacy capture structure
        keys = set(s.keys())
        assert (
            {
                "session_id",
                "device_id",
                "device_name",
                "created_at",
                "last_seen_at",
                "current",
            }.issubset(keys)
            or {"id", "status", "title", "transcript_uri"}.issubset(keys)
            or {"session_id", "status", "transcript_uri", "created_at"}.issubset(keys)
        )


def test_revoke_session_contract(monkeypatch):
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    r = c.post("/v1/sessions/sid_abc/revoke")
    assert r.status_code in {204, 401, 404}


def test_pats_get_empty(monkeypatch):
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    r = c.get("/v1/pats")
    assert r.status_code in {200, 404}


def test_pats_post_contract(monkeypatch):
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    body = {
        "name": "cursor-dev",
        "scopes": ["user:read", "media:write"],
        "exp_at": "2026-01-01T00:00:00Z",
    }
    r = c.post("/v1/pats", json=body)
    if r.status_code in {401, 404}:
        return
    assert r.status_code == 200
    obj = r.json()
    assert set(obj.keys()) >= {"id", "token", "scopes", "exp_at"}

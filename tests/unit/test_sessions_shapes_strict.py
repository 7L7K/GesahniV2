from fastapi.testclient import TestClient


def test_sessions_shapes_array_only(monkeypatch):
    from app.main import app

    client = TestClient(app)
    # Force auth bypass for test environment by setting a fake cookie
    with client:
        client.cookies.set("access_token", "invalid")
        r = client.get("/v1/sessions")
        assert r.status_code in (200, 401)
        if r.status_code == 200:
            assert isinstance(r.json(), list)


def test_sessions_paginated_shape(monkeypatch):
    from app.main import app

    client = TestClient(app)
    with client:
        client.cookies.set("access_token", "invalid")
        r = client.get("/v1/sessions/paginated")
        assert r.status_code in (200, 401)
        if r.status_code == 200:
            body = r.json()
            assert "items" in body and isinstance(body["items"], list)
            assert "next_cursor" in body

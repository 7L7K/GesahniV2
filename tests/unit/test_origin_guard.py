from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.origin_guard import OriginGuardMiddleware


def _build_app(allowed_origins=None):
    app = FastAPI()
    app.add_middleware(
        OriginGuardMiddleware, allowed_origins=allowed_origins or ["http://allowed.local"]
    )

    @app.post("/echo")
    def _echo():
        return {"status": "ok"}

    return app


def test_missing_origin_rejected():
    app = _build_app()
    client = TestClient(app)
    resp = client.post("/echo", headers={"Cookie": "session=1"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "origin_missing"


def test_allowed_origin_passes_and_sets_vary():
    app = _build_app(["http://frontend.local"])
    client = TestClient(app)
    resp = client.post(
        "/echo",
        headers={"Origin": "http://frontend.local", "Cookie": "session=1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    vary = resp.headers.get("Vary")
    assert vary is not None and "Origin" in vary


def test_referer_fallback_allows_when_origin_missing():
    app = _build_app(["http://frontend.local"])
    client = TestClient(app)
    resp = client.post(
        "/echo",
        headers={"Referer": "http://frontend.local/page", "Cookie": "session=1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_bad_origin_blocked():
    app = _build_app(["http://frontend.local"])
    client = TestClient(app)
    resp = client.post(
        "/echo",
        headers={
            "Origin": "http://evil.local",
            "Cookie": "session=1",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "bad_origin"

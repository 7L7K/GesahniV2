import json
from fastapi.testclient import TestClient
from app.main import create_app

app = create_app()
client = TestClient(app)

def test_404_envelope():
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.headers.get("X-Error-Code") == "not_found"
    body = r.json()
    assert body["code"] == "not_found"
    assert body["details"]["status_code"] == 404
    assert "trace_id" in body["details"]
    assert body["details"]["path"] == "/nope"
    assert body["details"]["method"] == "GET"

def test_422_envelope_and_legacy():
    # Send invalid payload to /v1/ask to trigger 422
    r = client.post("/v1/ask", json={"bad": "shape"})
    assert r.status_code == 422
    assert r.headers.get("X-Error-Code") == "invalid_input"
    body = r.json()
    # envelope
    assert body["code"] == "invalid_input"
    assert body["details"]["status_code"] == 422
    # classic fastapi fields
    assert body["detail"] == "Validation error"
    assert isinstance(body["errors"], list)

def test_500_envelope_retry_after(monkeypatch):
    # Create a route that raises
    from fastapi import APIRouter
    rt = APIRouter()
    @rt.get("/boom")
    def boom():
        raise RuntimeError("kaboom")
    app.include_router(rt)
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.headers.get("X-Error-Code") == "internal_error"
    body = r.json()
    assert body["code"] == "internal_error"
    assert "details" in body
    assert body["details"]["method"] == "GET"
    assert body["details"]["path"] == "/boom"

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_debug_headers_basic_shape():
    c = _client()
    r = c.get("/v1/debug/headers")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("headers"), dict)
    assert data.get("method") == "GET"
    assert isinstance(data.get("url"), str)


def test_debug_cookies_echo_and_presence_map():
    c = _client()
    # Set a few cookies first
    c.cookies.set("alpha", "1")
    c.cookies.set("beta", "")
    res = c.get("/v1/debug/cookies")
    assert res.status_code == 200
    body = res.json()
    assert "raw" in body and isinstance(body["raw"], str)
    assert isinstance(body.get("parsed"), dict)
    presence = body.get("presence") or {}
    assert presence.get("alpha") in {"present", ""}
    assert presence.get("beta") in {"present", ""}


def test_debug_whoami_full_unauthenticated():
    c = _client()
    res = c.get("/v1/debug/whoami/full")
    assert res.status_code == 200
    body = res.json()
    assert body.get("is_authenticated") in (False, True)
    assert isinstance(body.get("headers"), dict)
    assert isinstance(body.get("cookies"), dict)




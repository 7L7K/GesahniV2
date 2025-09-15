from starlette.testclient import TestClient

from app.main import create_app


def test_whoami_always_200_and_no_cookie_clear():
    """Test that /v1/whoami always returns 200 and doesn't clear cookies."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/v1/whoami")

    # Should always return 200
    assert response.status_code == 200

    # Should have the expected JSON structure
    body = response.json()
    assert "is_authenticated" in body
    assert "session_ready" in body
    assert "source" in body
    assert body["is_authenticated"] is False
    assert body["session_ready"] is False
    assert body["source"] == "missing"

    # Should not receive Set-Cookie headers that clear cookies
    set_cookie_headers = response.headers.get("set-cookie", "")
    assert "Max-Age=0" not in set_cookie_headers
    assert "expires=" not in set_cookie_headers.lower()


def test_whoami_unauthenticated_response():
    """Test /v1/whoami response when no authentication is present."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/v1/whoami")

    assert response.status_code == 200
    body = response.json()

    # Should indicate not authenticated
    assert body["is_authenticated"] is False
    assert body["session_ready"] is False
    assert body["user"]["id"] is None
    assert body["user"]["email"] is None
    assert "source" in body
    assert body["source"] == "missing"

from starlette.testclient import TestClient

from app.main import create_app


def test_me_missing_token_is_401():
    """Test that /v1/me returns 401 when no token is provided."""
    client = TestClient(create_app())
    response = client.get("/v1/me")

    assert response.status_code == 401
    body = response.json()
    assert "detail" in body
    assert "unauthorized" in body["detail"].lower()


def test_me_endpoint_exists():
    """Test that /v1/me endpoint exists and is properly registered."""
    app = create_app()
    routes = [r.path for r in app.routes if hasattr(r, "path")]

    assert "/v1/me" in routes


# Note: Add a 403 test with a token lacking scope if you have a test token fixture
# def test_me_insufficient_scope_is_403():
#     """Test that /v1/me returns 403 when token lacks required scope."""
#     client = TestClient(create_app())
#     # This would require a test token fixture with insufficient scope
#     # response = client.get("/v1/me", headers={"Authorization": "Bearer <insufficient_token>"})
#     # assert response.status_code == 403
#     pass

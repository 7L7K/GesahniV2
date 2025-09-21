"""Tests for trailing slash middleware functionality."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


class TestTrailingSlashMiddleware:
    """Test cases for trailing slash middleware."""

    def test_reminders_trailing_slash_redirect(self, client):
        """Test that /v1/reminders/ redirects to /v1/reminders with 308."""
        response = client.get("/v1/reminders/", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/reminders"

    def test_reminders_canonical_url_works(self, client):
        """Test that canonical URL /v1/reminders works correctly."""
        response = client.get("/v1/reminders", allow_redirects=False)
        assert response.status_code == 200

    def test_sessions_trailing_slash_redirect(self, client):
        """Test that /v1/sessions/ redirects to /v1/sessions with 308."""
        response = client.get("/v1/sessions/", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/sessions"

    def test_sessions_canonical_url_works(self, client):
        """Test that canonical URL /v1/sessions works correctly."""
        response = client.get("/v1/sessions", allow_redirects=False)
        # Sessions endpoint requires authentication, so 401 is expected
        assert response.status_code == 401

    def test_calendar_trailing_slash_redirect(self, client):
        """Test that /v1/calendar/ redirects to /v1/calendar with 308."""
        response = client.get("/v1/calendar/", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/calendar"

    def test_calendar_canonical_url_works(self, client):
        """Test that canonical URL /v1/calendar works correctly."""
        response = client.get("/v1/calendar", allow_redirects=False)
        # Calendar endpoint may not support GET method, so 405 is expected
        assert response.status_code == 405

    def test_root_path_not_redirected(self, client):
        """Test that root path / is not redirected."""
        response = client.get("/", allow_redirects=False)
        # Root path should work normally (might redirect to /docs)
        assert response.status_code in [200, 303, 307]

    def test_health_endpoints_not_redirected(self, client):
        """Test that health endpoints are not redirected."""
        health_paths = ["/healthz", "/livez", "/readyz"]
        for path in health_paths:
            response = client.get(path, allow_redirects=False)
            # Health endpoints should work normally (not be redirected)
            assert response.status_code in [200, 404]  # 404 if not implemented
        
        # /health should redirect to /healthz (this is expected behavior)
        response = client.get("/health", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/healthz"

    def test_openapi_docs_not_redirected(self, client):
        """Test that OpenAPI docs endpoints are not redirected."""
        docs_paths = ["/docs", "/redoc", "/openapi.json"]
        for path in docs_paths:
            response = client.get(path, allow_redirects=False)
            # Docs endpoints should work normally (not be redirected)
            assert response.status_code in [200, 404]  # 404 if not implemented

    def test_trailing_slash_preserves_query_params(self, client):
        """Test that trailing slash redirect preserves query parameters."""
        response = client.get("/v1/reminders/?limit=10&offset=0", allow_redirects=False)
        assert response.status_code == 308
        assert "limit=10" in response.headers["location"]
        assert "offset=0" in response.headers["location"]

    def test_trailing_slash_preserves_fragments(self, client):
        """Test that trailing slash redirect handles fragments (fragments are not sent to server)."""
        response = client.get("/v1/reminders/#section", allow_redirects=False)
        assert response.status_code == 308
        # Fragments are not sent to server in HTTP requests, so they won't be in Location header
        assert response.headers["location"] == "/v1/reminders"

    def test_trailing_slash_preserves_both_query_and_fragment(self, client):
        """Test that trailing slash redirect preserves query params (fragments are not sent to server)."""
        response = client.get("/v1/reminders/?limit=10#section", allow_redirects=False)
        assert response.status_code == 308
        location = response.headers["location"]
        assert "limit=10" in location
        # Fragments are not sent to server in HTTP requests, so they won't be in Location header
        assert "#section" not in location

    def test_multiple_trailing_slashes_handled(self, client):
        """Test that multiple trailing slashes are handled correctly."""
        response = client.get("/v1/reminders///", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/reminders"

    def test_post_method_preserved_in_redirect(self, client):
        """Test that POST method is preserved in 308 redirect."""
        response = client.post("/v1/reminders/", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/reminders"

    def test_put_method_preserved_in_redirect(self, client):
        """Test that PUT method is preserved in 308 redirect."""
        response = client.put("/v1/reminders/", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/reminders"

    def test_delete_method_preserved_in_redirect(self, client):
        """Test that DELETE method is preserved in 308 redirect."""
        response = client.delete("/v1/reminders/", allow_redirects=False)
        assert response.status_code == 308
        assert response.headers["location"] == "/v1/reminders"

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.deps.user import get_current_user_id
from app.models.user_stats import UserStats


def test_me_smoke():
    """Smoke test for /v1/me with mocked dependencies."""
    client = TestClient(app)

    # Override get_current_user_id
    async def mock_get_current_user_id():
        return "test_user"

    app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

    # Mock user_store.get_stats
    original_get_stats = None
    try:
        from app.user_store import user_store
        original_get_stats = user_store.get_stats

        async def mock_get_stats(user_id):
            return UserStats(
                user_id="test_user",
                login_count=7,
                request_count=42,
                last_login="2025-09-05T00:00:00Z"
            )

        user_store.get_stats = mock_get_stats

        # Test the endpoint
        response = client.get("/v1/me")
        assert response.status_code == 200

        data = response.json()
        assert "user" in data
        assert "stats" in data
        assert "sub" in data  # May be null

        assert data["user"]["id"] == "test_user"
        assert data["stats"]["login_count"] == 7
        assert data["stats"]["request_count"] == 42
        assert data["stats"]["last_login"] == "2025-09-05T00:00:00Z"

    finally:
        # Clean up overrides
        if get_current_user_id in app.dependency_overrides:
            del app.dependency_overrides[get_current_user_id]

        if original_get_stats is not None:
            from app.user_store import user_store
            user_store.get_stats = original_get_stats

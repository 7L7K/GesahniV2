from fastapi.testclient import TestClient

from app.main import app


def test_health_ready_degraded(monkeypatch):
    """Test health readiness endpoint returns degraded status when component is unhealthy."""

    # Set a proper JWT_SECRET for tests
    monkeypatch.setenv("JWT_SECRET", "test_jwt_secret_that_is_long_enough_for_validation_purposes_123456789")

    with TestClient(app) as client:
        # Mock the vector store to appear unhealthy
        class MockStore:
            def ping(self):
                # Simulate unhealthy state
                raise Exception("Vector store is down")

            def search_memories(self, *args, **kwargs):
                raise Exception("Vector store is down")

        # Patch the store getter to return our mock
        def mock_get_store():
            return MockStore()

        # Patch the vector store health check by mocking the health_utils functions
        def mock_vector_store_check():
            return "unhealthy"

        # Patch the health utilities that the health endpoint uses
        monkeypatch.setattr(
            "app.health_utils.check_db", lambda: "ok"
        )  # Keep DB healthy
        monkeypatch.setattr(
            "app.health_utils.check_jwt_secret", lambda: "ok"
        )  # Keep JWT healthy

        # Create a mock store that fails health checks
        original_get_store = None
        try:
            from app.memory.api import _get_store as original_get_store
        except ImportError:
            pass

        def failing_get_store():
            return MockStore()

        # Patch at the memory.api level where the health endpoint imports from
        if original_get_store:
            monkeypatch.setattr("app.memory.api._get_store", failing_get_store)

        # Make request to health readiness endpoint
        r = client.get("/healthz/ready")

        # Should return 503 when a required component is unhealthy
        assert r.status_code == 503

        data = r.json()

        # Should indicate unhealthy status when components fail
        assert data["status"] == "unhealthy"

        # Should include failing components in response
        assert "failing" in data
        assert isinstance(data["failing"], list)

        # At least one component should be unhealthy
        assert len(data["failing"]) > 0

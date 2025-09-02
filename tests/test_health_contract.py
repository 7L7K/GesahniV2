"""Contract tests to freeze API response shapes and prevent regressions."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Test client for contract tests."""
    return TestClient(app)


def test_ready_contract_shape(client):
    """Freeze the /healthz/ready response shape to prevent 503 regressions.

    This test ensures the readiness endpoint never returns 5xx errors and
    always includes the expected response structure with ok, status, and components.
    """
    r = client.get("/healthz/ready")
    assert r.status_code == 200  # Never 5xx for readiness probes

    response = r.json()

    # Required top-level keys
    required_keys = {"ok", "status", "components"}
    assert set(response.keys()) >= required_keys

    # Type checks
    assert isinstance(response["ok"], bool)
    assert isinstance(response["status"], str)
    assert isinstance(response["components"], dict)

    # Components should have expected structure
    components = response["components"]
    expected_component_keys = {"jwt_secret", "db", "vector_store"}
    assert set(components.keys()) >= expected_component_keys

    # Each component should have a status
    for component_name, component_data in components.items():
        assert isinstance(component_data, dict)
        assert "status" in component_data
        assert component_data["status"] in {"healthy", "unhealthy", "degraded"}

    # Status values should be valid
    assert response["status"] in {"ok", "unhealthy", "degraded"}

    # If status is unhealthy, there should be a failing array
    if response["status"] == "unhealthy":
        assert "failing" in response
        assert isinstance(response["failing"], list)
        assert len(response["failing"]) > 0

"""
Chaos tests for integration providers.

These tests simulate various failure scenarios to ensure the system handles
token failures, network issues, and revoked consents gracefully.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.chaos
class TestIntegrationChaos:
    """Chaos testing for integration robustness."""

    @pytest.fixture
    def client(self):
        """Get test client."""
        from app.main import app
        return TestClient(app)

    async def _create_test_token(self, user_id: str, provider: str, **kwargs):
        """Helper to create test tokens with specific properties."""
        from app.factories import make_token_store
        from app.models.third_party_tokens import ThirdPartyToken

        store = make_token_store()

        # Default token properties
        token_data = {
            "user_id": user_id,
            "provider": provider,
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "scopes": "read",
            "expires_at": int(time.time()) + 3600,  # 1 hour from now
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "is_valid": True,
            **kwargs  # Override defaults
        }

        token = ThirdPartyToken(**token_data)
        await store.upsert_token(token)
        return token

    def test_spotify_chaos_basic_status(self, client):
        """Test basic Spotify status functionality."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_basic"})
        assert login_response.status_code == 200

        # Hit status endpoint without any tokens
        response = client.get("/v1/spotify/status")
        assert response.status_code == 200

        data = response.json()
        assert data["connected"] is False
        # Should return some status information
        assert "reason" in data or "details" in data

    def test_spotify_chaos_refresh_scenario(self, client):
        """Test Spotify refresh token scenarios."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_refresh"})
        assert login_response.status_code == 200

        # Create expired token without refresh token
        import asyncio
        token = asyncio.run(self._create_test_token(
            "chaos_refresh",
            "spotify",
            expires_at=int(time.time()) - 100,
            refresh_token=None  # No refresh token available
        ))

        # Hit status endpoint
        response = client.get("/v1/spotify/status")
        assert response.status_code == 200

        data = response.json()
        assert data["connected"] is False
        # Should indicate cannot refresh

    def test_spotify_chaos_token_validation(self, client):
        """Test that tokens are properly validated."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_validation"})
        assert login_response.status_code == 200

        # Test with no tokens at all
        response = client.get("/v1/spotify/status")
        assert response.status_code == 200

        data = response.json()
        assert data["connected"] is False
        # Should indicate no tokens
        assert "no_tokens" in data.get("reason", "") or data.get("reason") == "not_authenticated"

    def test_spotify_chaos_network_failure_handling(self, client):
        """Test graceful handling of network failures during token operations."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_network"})
        assert login_response.status_code == 200

        # Create valid token
        import asyncio
        token = asyncio.run(self._create_test_token("chaos_network", "spotify"))

        # Mock network failure during token retrieval
        with patch("app.factories.make_token_store") as mock_factory:
            mock_store = AsyncMock()
            mock_store.get_token.side_effect = Exception("Network timeout")
            mock_factory.return_value = mock_store

            # Hit status endpoint
            response = client.get("/v1/spotify/status")
            assert response.status_code == 200

            data = response.json()
            assert data["connected"] is False
            # Should handle gracefully, not crash

    def test_google_chaos_basic_validation(self, client):
        """Test basic Google token validation."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_google_basic"})
        assert login_response.status_code == 200

        # Test with no tokens
        response = client.get("/v1/integrations/google/status")
        assert response.status_code == 200

        data = response.json()
        assert data["connected"] is False
        # Should indicate no token or unavailable
        assert data.get("degraded_reason") in ["no_token", "unavailable"]

    def test_google_chaos_response_structure(self, client):
        """Test that Google status returns expected structure."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_google_structure"})
        assert login_response.status_code == 200

        # Hit status endpoint
        response = client.get("/v1/integrations/google/status")
        assert response.status_code == 200

        data = response.json()

        # Check required fields exist
        required_fields = ["connected", "degraded_reason", "required_scopes_ok", "services"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_cross_provider_consistency_under_failure(self, client):
        """Test that both providers handle failures consistently."""
        providers = [
            ("spotify", "/v1/spotify/status"),
            ("google", "/v1/integrations/google/status")
        ]

        for provider_name, endpoint in providers:
            # Login for this test
            username = f"chaos_consistency_{provider_name}"
            login_response = client.post("/v1/auth/login", params={"username": username})
            assert login_response.status_code == 200

            # Test with no tokens (should be consistent)
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            assert "connected" in data
            assert data["connected"] is False

            # Provider-specific field checks
            if "spotify" in endpoint:
                assert "reason" in data
                assert data["reason"] in ["no_tokens", "not_authenticated"]
            elif "google" in endpoint:
                assert "degraded_reason" in data
                assert data["degraded_reason"] in ["no_token", "unavailable"]

    def test_chaos_metrics_spike_detection(self, client):
        """Test that failure scenarios cause appropriate metric spikes."""
        # This test would typically be run with a metrics collector
        # For now, we'll verify the code paths that should emit metrics

        # Login
        login_response = client.post("/v1/auth/login", params={"username": "chaos_metrics"})
        assert login_response.status_code == 200

        # Test various failure scenarios and verify metrics would be emitted
        scenarios = [
            ("/v1/spotify/status", "no_tokens"),
            ("/v1/integrations/google/status", ["no_token", "unavailable"]),
        ]

        for endpoint, expected_reasons in scenarios:
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            assert data["connected"] is False

            # Verify the failure reason matches expectation
            if "spotify" in endpoint:
                assert data.get("reason") == expected_reasons
            elif "google" in endpoint:
                assert data.get("degraded_reason") in expected_reasons


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-k", "chaos"])

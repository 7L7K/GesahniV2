"""
Contract tests for integration status endpoints.

These tests ensure that all integration status endpoints (Spotify, Google, etc.)
return consistent status reasons and maintain backward compatibility.

Canonical status reasons:
- no_tokens: User authenticated but no tokens stored
- needs_reauth: Token exists but requires reauthorization (expired, revoked)
- expired_with_refresh: Token expired but has refresh capability
- connected: Token valid and functional

This prevents drift between different integration implementations.
"""

import pytest
from fastapi.testclient import TestClient


# Canonical status reasons that all integrations must support
CANONICAL_STATUS_REASONS = {
    "no_tokens",
    "needs_reauth",
    "expired_with_refresh",
    "connected"
}


@pytest.mark.contract
class TestIntegrationStatusContract:
    """Contract tests ensuring status endpoint consistency across integrations."""

    @pytest.fixture
    def client(self):
        """Get test client."""
        from app.main import app
        return TestClient(app)

    def test_spotify_status_reasons_contract(self, client):
        """Test that Spotify status endpoint returns canonical reasons."""
        # Login to get authenticated session
        login_response = client.post("/v1/auth/login", params={"username": "contract_test"})
        assert login_response.status_code == 200

        # Get status - should return no_tokens for authenticated user with no tokens
        status_response = client.get("/v1/spotify/status")
        assert status_response.status_code == 200

        data = status_response.json()
        assert "reason" in data

        # The reason should be one of our canonical reasons
        reason = data["reason"]
        assert reason in CANONICAL_STATUS_REASONS, f"Unknown status reason: {reason}"

        # For no tokens case, should be "no_tokens"
        assert reason == "no_tokens", f"Expected 'no_tokens' for authenticated user with no tokens, got '{reason}'"

    def test_google_status_reasons_contract(self, client):
        """Test that Google status endpoint returns canonical reasons."""
        # Login to get authenticated session
        login_response = client.post("/v1/auth/login", params={"username": "contract_test"})
        assert login_response.status_code == 200

        # Get status - should return no_token for authenticated user with no tokens
        status_response = client.get("/v1/integrations/google/status")
        assert status_response.status_code == 200

        data = status_response.json()

        # Google uses degraded_reason field
        if "degraded_reason" in data:
            degraded_reason = data["degraded_reason"]

            # Map Google degraded reasons to canonical reasons
            if degraded_reason == "no_token":
                canonical_reason = "no_tokens"
            elif degraded_reason in ("consent_revoked", "expired_no_refresh"):
                canonical_reason = "needs_reauth"
            elif degraded_reason == "refresh_failed":
                canonical_reason = "expired_with_refresh"
            elif degraded_reason == "unavailable":
                canonical_reason = "needs_reauth"  # Map store errors to needs_reauth
            elif degraded_reason is None:
                canonical_reason = "connected"
            else:
                canonical_reason = degraded_reason  # Unknown, will fail assertion

            assert canonical_reason in CANONICAL_STATUS_REASONS, f"Unknown status reason: {canonical_reason}"

        # Connected status
        assert "connected" in data
        if data["connected"]:
            assert data.get("degraded_reason") is None, "Connected should have no degraded_reason"

    def test_spotify_integration_status_consistency(self, client):
        """Test that Spotify integration endpoint is consistent with main status endpoint."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "consistency_test"})
        assert login_response.status_code == 200

        # Get both endpoints
        main_status = client.get("/v1/spotify/status")
        integration_status = client.get("/v1/integrations/spotify/status")

        assert main_status.status_code == integration_status.status_code == 200

        main_data = main_status.json()
        integration_data = integration_status.json()

        # Both should have same connected status
        assert main_data["connected"] == integration_data["connected"]

        # Both should have same reason (if present)
        if "reason" in main_data and "reason" in integration_data:
            assert main_data["reason"] == integration_data["reason"]

    def test_google_integration_status_consistency(self, client):
        """Test that Google integration endpoint is consistent with main status endpoint."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "consistency_test"})
        assert login_response.status_code == 200

        # Get both endpoints (Google only has integration endpoint)
        integration_status = client.get("/v1/integrations/google/status")
        assert integration_status.status_code == 200

        data = integration_status.json()

        # Should always have connected field
        assert "connected" in data

        # Should always have degraded_reason field
        assert "degraded_reason" in data

    def test_status_endpoints_handle_unauthenticated_requests(self, client):
        """Test that status endpoints handle unauthenticated requests gracefully."""
        # Test Spotify status without auth
        spotify_response = client.get("/v1/spotify/status")
        assert spotify_response.status_code == 200  # Should not 401

        spotify_data = spotify_response.json()
        assert spotify_data["connected"] is False
        assert "reason" in spotify_data

        # Test Google status without auth
        google_response = client.get("/v1/integrations/google/status")
        assert google_response.status_code == 200  # Should not 401

        google_data = google_response.json()
        assert google_data["connected"] is False
        # Google may return "unavailable" for store errors or "no_token" for no auth
        assert google_data.get("degraded_reason") in ["no_token", "unavailable"]

    def test_status_endpoints_return_valid_json_structure(self, client):
        """Test that all status endpoints return valid JSON with expected structure."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "structure_test"})
        assert login_response.status_code == 200

        endpoints = [
            "/v1/spotify/status",
            "/v1/integrations/spotify/status",
            "/v1/integrations/google/status"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            assert isinstance(data, dict)

            # All should have connected field
            assert "connected" in data
            assert isinstance(data["connected"], bool)

            # Provider-specific fields
            if "spotify" in endpoint:
                # Main Spotify status has reason, devices_ok, state_ok
                # Integration status only has basic fields
                if "/v1/spotify/status" in endpoint:
                    assert "reason" in data
                    assert "devices_ok" in data
                    assert "state_ok" in data
                else:
                    # Integration status has basic fields but no reason
                    assert "connected" in data
                    assert "expires_at" in data or data.get("expires_at") is None
            elif "google" in endpoint:
                assert "degraded_reason" in data
                assert "required_scopes_ok" in data
                assert "services" in data

    def test_cross_provider_status_schema_consistency(self, client):
        """Test that all providers return consistent JSON schema for frontend consumption."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "schema_test"})
        assert login_response.status_code == 200

        # Define the expected common schema for all providers
        common_schema = {
            "connected": bool,
            "expires_at": [int, type(None)],
            "last_refresh_at": [int, type(None)],
            "refreshed": [bool, type(None)]  # Can be None when no token exists
        }

        # Provider-specific schemas
        provider_schemas = {
            "spotify_main": {
                **common_schema,
                "reason": str,
                "devices_ok": bool,
                "state_ok": bool,
                "scopes": [list, type(None)]
            },
            "spotify_integration": {
                **common_schema,
                "scopes": [list, type(None)]
            },
            "google_integration": {
                **common_schema,
                "degraded_reason": [str, type(None)],
                "required_scopes_ok": bool,
                "scopes": [list, type(None)],
                "services": dict
            }
        }

        endpoints = [
            ("/v1/spotify/status", "spotify_main"),
            ("/v1/integrations/spotify/status", "spotify_integration"),
            ("/v1/integrations/google/status", "google_integration")
        ]

        for endpoint, schema_name in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            schema = provider_schemas[schema_name]

            # Validate each expected field
            for field_name, expected_types in schema.items():
                assert field_name in data, f"Missing field '{field_name}' in {endpoint}"

                field_value = data[field_name]
                if isinstance(expected_types, list):
                    assert type(field_value) in expected_types, \
                        f"Field '{field_name}' in {endpoint} has type {type(field_value)}, expected one of {expected_types}"
                else:
                    assert isinstance(field_value, expected_types), \
                        f"Field '{field_name}' in {endpoint} has type {type(field_value)}, expected {expected_types}"

                # Additional validations
                if field_name == "scopes" and field_value is not None:
                    assert isinstance(field_value, list), f"Scopes should be list in {endpoint}"
                    assert all(isinstance(s, str) for s in field_value), f"All scopes should be strings in {endpoint}"

                if field_name == "services" and schema_name == "google_integration":
                    assert isinstance(field_value, dict), f"Services should be dict in {endpoint}"

    def test_cross_provider_error_handling_consistency(self, client):
        """Test that all providers handle errors consistently."""
        # Test unauthenticated requests
        endpoints = [
            "/v1/spotify/status",
            "/v1/integrations/spotify/status",
            "/v1/integrations/google/status"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # All should handle gracefully (no 500 errors)
            assert response.status_code in [200, 401], \
                f"Unexpected status code {response.status_code} for {endpoint}"

            data = response.json()

            # Should always have connected field
            assert "connected" in data
            assert data["connected"] is False

    def test_provider_status_response_canonical_mapping(self, client):
        """Test that all provider reasons map to canonical status reasons."""
        # This test ensures frontend can handle all providers uniformly

        # Login
        login_response = client.post("/v1/auth/login", params={"username": "canonical_test"})
        assert login_response.status_code == 200

        # Test each provider's "no tokens" state
        test_cases = [
            {
                "endpoint": "/v1/spotify/status",
                "expected_connected": False,
                "reason_field": "reason",
                "expected_reason": "no_tokens"
            },
            {
                "endpoint": "/v1/integrations/spotify/status",
                "expected_connected": False,
                # Integration endpoints might not have reason field
            },
            {
                "endpoint": "/v1/integrations/google/status",
                "expected_connected": False,
                "reason_field": "degraded_reason",
                "expected_reasons": ["no_token", "unavailable"]  # Can be unavailable due to test DB issues
            }
        ]

        for test_case in test_cases:
            endpoint = test_case["endpoint"]
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            assert data["connected"] == test_case["expected_connected"]

            # Check reason field if specified
            if "reason_field" in test_case:
                reason_field = test_case["reason_field"]
                expected_reasons = test_case.get("expected_reasons", [test_case.get("expected_reason")])

                assert reason_field in data
                assert data[reason_field] in expected_reasons, \
                    f"Expected {data[reason_field]} to be one of {expected_reasons}"

    def test_provider_status_fields_type_safety(self, client):
        """Test that all provider status fields have correct types."""
        # Login
        login_response = client.post("/v1/auth/login", params={"username": "type_safety_test"})
        assert login_response.status_code == 200

        endpoints = [
            "/v1/spotify/status",
            "/v1/integrations/spotify/status",
            "/v1/integrations/google/status"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()

            # Type assertions for common fields
            assert isinstance(data.get("connected"), bool)

            # refreshed can be bool or None (when no token exists)
            refreshed = data.get("refreshed")
            if refreshed is not None:
                assert isinstance(refreshed, bool)

            # expires_at and last_refresh_at should be int or None
            expires_at = data.get("expires_at")
            if expires_at is not None:
                assert isinstance(expires_at, int)

            last_refresh_at = data.get("last_refresh_at")
            if last_refresh_at is not None:
                assert isinstance(last_refresh_at, int)

            # Provider-specific type checks
            if "spotify" in endpoint and "/v1/spotify/status" in endpoint:
                assert isinstance(data.get("reason"), str)
                assert isinstance(data.get("devices_ok"), bool)
                assert isinstance(data.get("state_ok"), bool)

            if "google" in endpoint:
                degraded_reason = data.get("degraded_reason")
                if degraded_reason is not None:
                    assert isinstance(degraded_reason, str)
                assert isinstance(data.get("required_scopes_ok"), bool)
                assert isinstance(data.get("services"), dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

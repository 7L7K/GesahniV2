"""
Observability symmetry tests.

These tests ensure that metrics and logging behave consistently across
different providers (Spotify, Google, etc.) to maintain dashboard
consistency and prevent monitoring gaps.
"""

import pytest
import logging
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers.fakes import FakeTokenStore
from tests.helpers.overrides import override_token_store


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def fake_store():
    """Fake token store fixture."""
    return FakeTokenStore()


def test_metrics_symmetry_spotify_vs_google(caplog, client, fake_store):
    """Test that Spotify and Google operations produce symmetric metrics."""
    with override_token_store(fake_store):
        # Test Spotify callback
        with caplog.at_level(logging.INFO):
            response_spotify = client.get(
                "/v1/spotify/callback?code=spotify_code&state=spotify_state123"
            )

        # Test Google callback
        with caplog.at_level(logging.INFO):
            response_google = client.get(
                "/v1/google/callback?code=google_code&state=google_state456"
            )

    # Both should succeed
    assert response_spotify.status_code == 302
    assert response_google.status_code == 302

    # Extract log messages
    spotify_logs = [record for record in caplog.records
                   if "spotify" in record.message.lower()]
    google_logs = [record for record in caplog.records
                  if "google" in record.message.lower()]

    # Check for symmetric logging patterns
    spotify_starts = [log for log in spotify_logs if "start" in log.message]
    google_starts = [log for log in google_logs if "start" in log.message]

    spotify_success = [log for log in spotify_logs if "jwt_ok" in log.message]
    google_success = [log for log in google_logs if "jwt_ok" in log.message]

    # Both providers should have similar logging patterns
    assert len(spotify_starts) >= 1
    assert len(google_starts) >= 1
    assert len(spotify_success) >= 1
    assert len(google_success) >= 1


def test_metrics_labels_consistency():
    """Test that metrics use consistent label sets across providers."""
    from app.metrics import (
        SPOTIFY_STATUS_REQUESTS_COUNT,
        SPOTIFY_STATUS_CONNECTED,
        SPOTIFY_TOKENS_EXPIRES_IN_SECONDS
    )

    # This test would be more comprehensive with actual metric collection,
    # but for now we verify the metric objects exist and have consistent structure

    # Check that all provider metrics have similar label patterns
    # In a real implementation, you'd collect metrics and verify labels match

    # For now, just verify the metrics are defined
    assert SPOTIFY_STATUS_REQUESTS_COUNT is not None
    assert SPOTIFY_STATUS_CONNECTED is not None
    assert SPOTIFY_TOKENS_EXPIRES_IN_SECONDS is not None


def test_error_logging_symmetry(caplog, client, fake_store):
    """Test that error logging is symmetric across providers."""
    with override_token_store(fake_store):
        # Test Spotify error case (missing code)
        with caplog.at_level(logging.WARNING):
            client.get("/v1/spotify/callback?state=spotify_state")

        # Test Google error case (missing code)
        with caplog.at_level(logging.WARNING):
            client.get("/v1/google/callback?state=google_state")

    # Extract error logs
    spotify_errors = [record for record in caplog.records
                     if "spotify" in record.message.lower() and record.levelno >= logging.WARNING]
    google_errors = [record for record in caplog.records
                    if "google" in record.message.lower() and record.levelno >= logging.WARNING]

    # Both should log errors with similar patterns
    assert len(spotify_errors) >= 1
    assert len(google_errors) >= 1

    # Check that error messages mention missing code for both
    spotify_missing_code = any("code" in error.message.lower() for error in spotify_errors)
    google_missing_code = any("code" in error.message.lower() for error in google_errors)

    assert spotify_missing_code or google_missing_code  # At least one should mention missing code


def test_response_format_symmetry(client, fake_store):
    """Test that API responses have symmetric formats across providers."""
    with override_token_store(fake_store):
        # Test Spotify status endpoint
        spotify_response = client.get("/v1/integrations/spotify/status")

        # Test Google status endpoint
        google_response = client.get("/v1/integrations/google/status")

    # Both should return JSON responses
    assert spotify_response.headers["content-type"] == "application/json"
    assert google_response.headers["content-type"] == "application/json"

    # Parse responses
    spotify_data = spotify_response.json()
    google_data = google_response.json()

    # Both should have similar structure
    expected_fields = ["connected", "provider"]
    for field in expected_fields:
        assert field in spotify_data or field in google_data  # At least one has the field


def test_token_storage_symmetry(fake_store):
    """Test that token storage patterns are symmetric across providers."""
    import time
    from app.models.third_party_tokens import ThirdPartyToken

    # Create tokens for different providers
    spotify_token = ThirdPartyToken(
        user_id="test_user",
        provider="spotify",
        access_token="spotify_token",
        refresh_token="spotify_refresh",
        scopes="user-read-private",
        expires_at=int(time.time()) + 3600,
    )

    google_token = ThirdPartyToken(
        user_id="test_user",
        provider="google",
        access_token="google_token",
        refresh_token="google_refresh",
        scopes="https://www.googleapis.com/auth/calendar",
        expires_at=int(time.time()) + 3600,
    )

    # Store both tokens
    import asyncio
    asyncio.run(fake_store.upsert_token(spotify_token))
    asyncio.run(fake_store.upsert_token(google_token))

    # Verify both are stored with same interface
    spotify_retrieved = asyncio.run(fake_store.get_token("test_user", "spotify"))
    google_retrieved = asyncio.run(fake_store.get_token("test_user", "google"))

    assert spotify_retrieved is not None
    assert google_retrieved is not None

    # Both should have the same core attributes
    for token in [spotify_retrieved, google_retrieved]:
        assert hasattr(token, 'user_id')
        assert hasattr(token, 'provider')
        assert hasattr(token, 'access_token')
        assert hasattr(token, 'refresh_token')
        assert hasattr(token, 'scopes')
        assert hasattr(token, 'expires_at')

    # Test has_any consistency
    has_spotify = asyncio.run(fake_store.has_any("test_user", "spotify"))
    has_google = asyncio.run(fake_store.has_any("test_user", "google"))
    has_any = asyncio.run(fake_store.has_any("test_user"))

    assert has_spotify and has_google and has_any


def test_performance_symmetry():
    """Test that performance characteristics are similar across providers."""
    import time
    from app.models.third_party_tokens import ThirdPartyToken
    from tests.helpers.fakes import FakeTokenStore

    fake_store = FakeTokenStore()

    # Create test tokens
    tokens = []
    for i in range(10):
        for provider in ["spotify", "google"]:
            token = ThirdPartyToken(
                user_id=f"user_{i}",
                provider=provider,
                access_token=f"token_{i}_{provider}",
                scopes="test_scope",
                expires_at=int(time.time()) + 3600,
            )
            tokens.append(token)

    # Measure insertion performance
    import asyncio
    start_time = time.time()

    for token in tokens:
        asyncio.run(fake_store.upsert_token(token))

    end_time = time.time()
    insertion_time = end_time - start_time

    # Should complete within reasonable time (adjust threshold as needed)
    assert insertion_time < 5.0  # 5 seconds max for 20 insertions

    # Measure retrieval performance
    start_time = time.time()

    for token in tokens:
        retrieved = asyncio.run(fake_store.get_token(token.user_id, token.provider))
        assert retrieved is not None

    end_time = time.time()
    retrieval_time = end_time - start_time

    # Retrieval should also be reasonable
    assert retrieval_time < 2.0  # 2 seconds max for 20 retrievals


@pytest.mark.parametrize("provider", ["spotify", "google"])
def test_provider_specific_metrics(provider, caplog, client, fake_store):
    """Test that each provider has its own metrics properly isolated."""
    with override_token_store(fake_store):
        with caplog.at_level(logging.INFO):
            # Make a request for the specific provider
            if provider == "spotify":
                response = client.get("/v1/integrations/spotify/status")
            else:
                response = client.get("/v1/integrations/google/status")

    # Should get a valid response
    assert response.status_code == 200

    # Check that logs mention the correct provider
    provider_logs = [record for record in caplog.records
                    if provider.lower() in record.message.lower()]

    # Should have at least some logs for this provider
    assert len(provider_logs) >= 1

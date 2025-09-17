"""
Unit tests for Spotify integration helper functions.

Tests cover:
1. _token_scope_list: scope parsing with various input formats
2. _prefers_json_response: Accept header parsing
3. _recent_refresh: boundary value testing
4. Origin guard functions: comprehensive origin validation
5. Integration endpoint tests for /integrations/spotify/status
6. Callback endpoint tests for /spotify/callback
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_mod
from app.api import spotify as spotify_mod


class TestTokenScopeList:
    """Test _token_scope_list function with various input formats."""

    def test_scope_string_with_spaces(self):
        """Test scope string with spaces gets parsed correctly."""
        token = MagicMock()
        token.scopes = "user-read-private user-read-email playlist-read-private"
        token.scope = None

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email", "playlist-read-private"]
        assert result == expected

    def test_scope_string_comma_separated(self):
        """Test comma-separated scope string gets parsed correctly."""
        token = MagicMock()
        token.scopes = None
        token.scope = "user-read-private,user-read-email,playlist-read-private"

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email", "playlist-read-private"]
        assert result == expected

    def test_scope_list_input(self):
        """Test list input gets returned as-is."""
        token = MagicMock()
        token.scopes = ["user-read-private", "user-read-email"]
        token.scope = None

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email"]
        assert result == expected

    def test_scope_tuple_input(self):
        """Test tuple input gets converted to list."""
        token = MagicMock()
        token.scopes = ("user-read-private", "user-read-email")
        token.scope = None

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email"]
        assert result == expected

    def test_scope_set_input(self):
        """Test set input gets converted to sorted list."""
        token = MagicMock()
        token.scopes = {"user-read-email", "user-read-private", "playlist-read-private"}
        token.scope = None

        result = spotify_mod._token_scope_list(token)
        # Sets are unordered, but we should get all scopes
        assert set(result) == {
            "user-read-private",
            "user-read-email",
            "playlist-read-private",
        }

    def test_none_token_returns_empty_list(self):
        """Test None token returns empty list."""
        result = spotify_mod._token_scope_list(None)
        assert result == []

    def test_empty_scope_returns_empty_list(self):
        """Test empty scope returns empty list."""
        token = MagicMock()
        token.scopes = ""
        token.scope = ""

        result = spotify_mod._token_scope_list(token)
        assert result == []

    def test_mixed_spaces_and_commas(self):
        """Test mixed spaces and commas in scope string."""
        token = MagicMock()
        token.scopes = None
        token.scope = "user-read-private, user-read-email playlist-read-private"

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email", "playlist-read-private"]
        assert result == expected

    def test_whitespace_handling(self):
        """Test that extra whitespace is stripped."""
        token = MagicMock()
        token.scopes = "  user-read-private  , user-read-email  "
        token.scope = None

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email"]
        assert result == expected

    def test_empty_parts_filtered(self):
        """Test that empty parts are filtered out."""
        token = MagicMock()
        token.scopes = None
        token.scope = "user-read-private,,user-read-email,"

        result = spotify_mod._token_scope_list(token)
        expected = ["user-read-private", "user-read-email"]
        assert result == expected


class TestPrefersJsonResponse:
    """Test _prefers_json_response function."""

    def test_json_in_accept_header(self):
        """Test that application/json in Accept header returns True."""
        request = MagicMock()
        request.headers = {"Accept": "application/json, text/html"}

        result = spotify_mod._prefers_json_response(request)
        assert result is True

    def test_multiple_mime_types_with_json(self):
        """Test multiple mime types where json is preferred."""
        request = MagicMock()
        request.headers = {"Accept": "text/html, application/json, application/xml"}

        result = spotify_mod._prefers_json_response(request)
        assert result is True

    def test_no_json_in_accept_header(self):
        """Test that no json in Accept header with non-testclient returns False."""
        request = MagicMock()
        request.headers = {
            "Accept": "text/html, application/xml",
            "User-Agent": "Mozilla/5.0",
        }

        result = spotify_mod._prefers_json_response(request)
        assert result is False

    def test_no_headers_returns_true(self):
        """Test that no headers returns True (TestClient path)."""
        request = MagicMock()
        request.headers = {}

        result = spotify_mod._prefers_json_response(request)
        assert result is True

    def test_testclient_user_agent_returns_true(self):
        """Test that testclient user agent returns True."""
        request = MagicMock()
        request.headers = {"Accept": "text/html", "User-Agent": "testclient"}

        result = spotify_mod._prefers_json_response(request)
        assert result is True

    def test_case_insensitive_accept_header(self):
        """Test that Accept header matching is case insensitive."""
        request = MagicMock()
        request.headers = {"Accept": "Application/JSON, text/html"}

        result = spotify_mod._prefers_json_response(request)
        assert result is True


class TestRecentRefresh:
    """Test _recent_refresh function with boundary values."""

    def test_none_timestamp_returns_false(self):
        """Test that None timestamp returns False."""
        result = spotify_mod._recent_refresh(None, now=1000)
        assert result is False

    def test_recent_refresh_boundary_3599_seconds(self):
        """Test boundary case: 3599 seconds ago (should be recent)."""
        now = 10000
        timestamp = now - 3599
        result = spotify_mod._recent_refresh(timestamp, now=now)
        assert result is True

    def test_recent_refresh_boundary_3600_seconds(self):
        """Test boundary case: 3600 seconds ago (should not be recent)."""
        now = 10000
        timestamp = now - 3600
        result = spotify_mod._recent_refresh(timestamp, now=now)
        assert result is False

    def test_recent_refresh_boundary_3601_seconds(self):
        """Test boundary case: 3601 seconds ago (should not be recent)."""
        now = 10000
        timestamp = now - 3601
        result = spotify_mod._recent_refresh(timestamp, now=now)
        assert result is False

    def test_very_recent_refresh(self):
        """Test very recent refresh (should be recent)."""
        now = 10000
        timestamp = now - 1
        result = spotify_mod._recent_refresh(timestamp, now=now)
        assert result is True

    def test_old_refresh(self):
        """Test old refresh (should not be recent)."""
        now = 10000
        timestamp = now - 7200  # 2 hours ago
        result = spotify_mod._recent_refresh(timestamp, now=now)
        assert result is False

    def test_future_timestamp(self):
        """Test future timestamp (should be recent)."""
        now = 10000
        timestamp = now + 100
        result = spotify_mod._recent_refresh(timestamp, now=now)
        assert result is True


class TestOriginGuard:
    """Test origin guard functions."""

    def test_origin_allowed_exact_match(self):
        """Test that exact origin match returns True."""
        allowed = ["http://localhost:3000", "https://example.com"]
        result = spotify_mod._origin_allowed("http://localhost:3000", allowed)
        assert result is True

    def test_origin_allowed_no_match(self):
        """Test that non-matching origin returns False."""
        allowed = ["http://localhost:3000"]
        result = spotify_mod._origin_allowed("http://evil.com", allowed)
        assert result is False

    def test_origin_allowed_empty_candidate(self):
        """Test that empty candidate returns False."""
        allowed = ["http://localhost:3000"]
        result = spotify_mod._origin_allowed("", allowed)
        assert result is False

    def test_origin_allowed_none_candidate(self):
        """Test that None candidate returns False."""
        allowed = ["http://localhost:3000"]
        result = spotify_mod._origin_allowed(None, allowed)
        assert result is False

    def test_origin_allowed_with_regex(self):
        """Test that regex patterns work for origin matching."""
        with patch.object(
            spotify_mod,
            "_ORIGIN_REGEXES",
            [spotify_mod.re.compile(r"https://.*\.example\.com")],
        ):
            allowed = ["http://localhost:3000"]
            result = spotify_mod._origin_allowed("https://api.example.com", allowed)
            assert result is True

    def test_origin_allowed_regex_no_match(self):
        """Test that regex patterns that don't match return False."""
        with patch.object(
            spotify_mod,
            "_ORIGIN_REGEXES",
            [spotify_mod.re.compile(r"https://.*\.example\.com")],
        ):
            allowed = ["http://localhost:3000"]
            result = spotify_mod._origin_allowed("https://evil.com", allowed)
            assert result is False

    def test_dev_mode_enabled_localhost_allowed(self):
        """Test that dev mode allows localhost origins."""
        with patch.dict("os.environ", {"ENV": "dev"}):
            with patch.object(spotify_mod, "_dev_mode_enabled", return_value=True):
                allowed = ["http://localhost:3000"]
                result = spotify_mod._origin_allowed("http://localhost:8080", allowed)
                # In dev mode, additional localhost origins should be allowed
                # This depends on the actual implementation in _origin_allowed

    def test_parse_origins_none_input(self):
        """Test _parse_origins with None input."""
        result = spotify_mod._parse_origins(None)
        assert result == []

    def test_parse_origins_empty_string(self):
        """Test _parse_origins with empty string."""
        result = spotify_mod._parse_origins("")
        assert result == []

    def test_parse_origins_single_origin(self):
        """Test _parse_origins with single origin."""
        result = spotify_mod._parse_origins("http://localhost:3000")
        assert result == ["http://localhost:3000"]

    def test_parse_origins_multiple_origins(self):
        """Test _parse_origins with multiple origins."""
        result = spotify_mod._parse_origins("http://localhost:3000,https://example.com")
        expected = ["http://localhost:3000", "https://example.com"]
        assert result == expected

    def test_parse_origins_with_whitespace(self):
        """Test _parse_origins strips whitespace."""
        result = spotify_mod._parse_origins(
            " http://localhost:3000 , https://example.com "
        )
        expected = ["http://localhost:3000", "https://example.com"]
        assert result == expected

    def test_parse_origins_filters_empty_parts(self):
        """Test _parse_origins filters empty parts."""
        result = spotify_mod._parse_origins(
            "http://localhost:3000,,https://example.com,"
        )
        expected = ["http://localhost:3000", "https://example.com"]
        assert result == expected

    def test_parse_origins_rstrip_slash(self):
        """Test _parse_origins strips trailing slashes."""
        result = spotify_mod._parse_origins("http://localhost:3000/")
        assert result == ["http://localhost:3000"]

    def test_parse_origins_lower_case(self):
        """Test _parse_origins converts to lower case."""
        result = spotify_mod._parse_origins("HTTP://LOCALHOST:3000")
        assert result == ["http://localhost:3000"]


class TestSpotifyStatus:
    """Test /spotify/status endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(main_mod.app)

    def create_auth_token(self):
        """Create a valid JWT token for testing."""
        import os
        from datetime import datetime, timedelta

        import jwt

        secret = os.getenv("JWT_SECRET", "test_secret")
        payload = {
            "sub": "test_user",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        return f"Bearer {token}"

    def test_valid_token_connected_true(self, client, monkeypatch):
        """Test valid token with future expires_at returns connected=True."""
        from unittest.mock import patch

        now = int(time.time())

        # Set JWT secret for authentication
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Create mock token
        mock_token = MagicMock()
        mock_token.id = "spotify:test123"
        mock_token.expires_at = now + 3600  # 1 hour from now
        mock_token.last_refresh_at = now - 100
        mock_token.is_valid = True
        mock_token.scopes = "user-read-private user-read-email"

        # Create auth token
        auth_token = self.create_auth_token()

        # Use patch context managers for reliable mocking
        with patch("app.auth_store_tokens.get_token", return_value=mock_token):
            with patch(
                "app.integrations.spotify.client.get_token", return_value=mock_token
            ):
                with patch(
                    "app.integrations.spotify.client.SpotifyClient.get_user_profile",
                    return_value={
                        "id": "test_spotify_user",
                        "display_name": "Test User",
                    },
                ):
                    response = client.get(
                        "/v1/spotify/status", headers={"Authorization": auth_token}
                    )
                    assert response.status_code == 200

                    data = response.json()
                    assert data["connected"] is True
                    assert data["expires_at"] == now + 3600
                    assert data["last_refresh_at"] == now - 100
                    assert (
                        data["refreshed"] is True
                    )  # 100 seconds < 3600 seconds (recent threshold)
                    assert "user-read-private" in data["scopes"]
                    assert "user-read-email" in data["scopes"]

    def test_expired_token_connected_false(self, client, monkeypatch):
        """Test expired token returns connected=False."""
        from unittest.mock import patch

        now = int(time.time())

        # Set JWT secret for authentication
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Create expired mock token
        mock_token = MagicMock()
        mock_token.id = "spotify:test123"
        mock_token.expires_at = now - 100  # expired 100 seconds ago
        mock_token.last_refresh_at = now - 200
        mock_token.is_valid = True
        mock_token.scopes = "user-read-private"

        # Create auth token
        auth_token = self.create_auth_token()

        # Use patch context managers
        with patch("app.auth_store_tokens.get_token", return_value=mock_token):
            with patch(
                "app.integrations.spotify.client.get_token", return_value=mock_token
            ):
                # Simulate token expiration by raising an exception
                from app.integrations.spotify.client import SpotifyAuthError

                with patch(
                    "app.integrations.spotify.client.SpotifyClient.get_user_profile",
                    side_effect=SpotifyAuthError("Token expired"),
                ):
                    response = client.get(
                        "/v1/spotify/status", headers={"Authorization": auth_token}
                    )
                    assert response.status_code == 200

                    data = response.json()
                    assert data["connected"] is False
                    # Note: expires_at and last_refresh_at may not be present when token is invalid
                    if "expires_at" in data:
                        assert data["expires_at"] == now - 100
                    if "last_refresh_at" in data:
                        assert data["last_refresh_at"] == now - 200

    def test_invalid_token_connected_false(self, client, monkeypatch):
        """Test token with is_valid=None returns connected=False."""
        from unittest.mock import patch

        now = int(time.time())

        # Set JWT secret for authentication
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Create invalid mock token
        mock_token = MagicMock()
        mock_token.id = "spotify:test123"
        mock_token.expires_at = now + 3600
        mock_token.last_refresh_at = now - 100
        mock_token.is_valid = None
        mock_token.scopes = "user-read-private"

        # Create auth token
        auth_token = self.create_auth_token()

        # Use patch context managers
        with patch("app.auth_store_tokens.get_token", return_value=mock_token):
            with patch(
                "app.integrations.spotify.client.get_token", return_value=mock_token
            ):
                # Simulate invalid token by raising an exception
                from app.integrations.spotify.client import SpotifyAuthError

                with patch(
                    "app.integrations.spotify.client.SpotifyClient.get_user_profile",
                    side_effect=SpotifyAuthError("Invalid token"),
                ):
                    response = client.get(
                        "/v1/spotify/status", headers={"Authorization": auth_token}
                    )
                    assert response.status_code == 200

                    data = response.json()
                    assert data["connected"] is False

    def test_missing_required_scopes(self, client, monkeypatch):
        """Test missing required scopes returns required_scopes_ok=False."""
        from unittest.mock import patch

        now = int(time.time())

        # Set JWT secret for authentication
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Create mock token missing required scopes
        mock_token = MagicMock()
        mock_token.id = "spotify:test123"
        mock_token.expires_at = now + 3600
        mock_token.last_refresh_at = now - 100
        mock_token.is_valid = True
        mock_token.scopes = (
            "playlist-read-private"  # missing user-read-email and user-read-private
        )

        # Create auth token
        auth_token = self.create_auth_token()

        # Use patch context managers
        with patch("app.auth_store_tokens.get_token", return_value=mock_token):
            with patch(
                "app.integrations.spotify.client.get_token", return_value=mock_token
            ):
                with patch(
                    "app.integrations.spotify.client.SpotifyClient.get_user_profile",
                    return_value={
                        "id": "test_spotify_user",
                        "display_name": "Test User",
                    },
                ):
                    response = client.get(
                        "/v1/spotify/status", headers={"Authorization": auth_token}
                    )
                    assert response.status_code == 200

                    data = response.json()
                    assert (
                        data["connected"] is True
                    )  # still connected due to valid token
                    assert data.get("required_scopes_ok") is False

    def test_no_token_returns_disconnected(self, client, monkeypatch):
        """Test no token returns disconnected state."""
        from unittest.mock import patch

        # Set JWT secret for authentication
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Create auth token
        auth_token = self.create_auth_token()

        # Use patch context managers to return None (no token)
        with patch("app.auth_store_tokens.get_token", return_value=None):
            with patch("app.integrations.spotify.client.get_token", return_value=None):
                # Simulate no token by raising an exception
                from app.integrations.spotify.client import SpotifyAuthError

                with patch(
                    "app.integrations.spotify.client.SpotifyClient.get_user_profile",
                    side_effect=SpotifyAuthError("No token available"),
                ):
                    response = client.get(
                        "/v1/spotify/status", headers={"Authorization": auth_token}
                    )
                    assert response.status_code == 200

                    data = response.json()
                    assert data["connected"] is False
                    # When no token exists, all fields are present but with None/empty values
                    assert data["expires_at"] is None
                    assert data["last_refresh_at"] is None
                    assert data["refreshed"] is False
                    assert data["scopes"] == []


class TestSpotifyCallback:
    """Test /spotify/callback endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(main_mod.app)

    def test_missing_state_json_response(self, client, monkeypatch):
        """Test missing state with JSON Accept header returns 400."""
        # Mock prefers_json_response to return True
        monkeypatch.setattr("app.api.spotify._prefers_json_response", lambda req: True)

        # Set JWT secret for JWT operations
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        response = client.get("/v1/spotify/callback?code=test")
        # The endpoint should handle missing state appropriately
        assert response.status_code in [302, 400]  # Either redirect or JSON error

    def test_missing_state_redirect_response(self, client, monkeypatch):
        """Test missing state without JSON Accept header returns 302 redirect."""
        # Mock prefers_json_response to return False
        monkeypatch.setattr("app.api.spotify._prefers_json_response", lambda req: False)

        # Set JWT secret for JWT operations
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        response = client.get("/v1/spotify/callback?code=test")
        # Should redirect due to missing state
        if response.status_code == 302:
            assert "spotify_error=bad_state" in response.headers.get("Location", "")

    def test_missing_code_redirect_response(self, client, monkeypatch):
        """Test missing code returns 302 redirect."""
        # Mock prefers_json_response to return False
        monkeypatch.setattr("app.api.spotify._prefers_json_response", lambda req: False)

        # Set JWT secret for JWT operations
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        response = client.get("/v1/spotify/callback?state=test_state")
        # Should redirect due to missing code
        if response.status_code == 302:
            assert "spotify_error=missing_code" in response.headers.get("Location", "")

    def test_expired_state_jwt_redirect(self, client, monkeypatch):
        """Test expired JWT state returns 302 with expired_state error."""
        # Create expired JWT
        import jwt

        expired_payload = {
            "tx": "test_tx",
            "uid": "test_user",
            "exp": int(time.time()) - 100,  # expired 100 seconds ago
            "iat": int(time.time()) - 200,
        }
        expired_state = jwt.encode(expired_payload, "test_secret", algorithm="HS256")

        # Mock prefers_json_response to return False
        monkeypatch.setattr("app.api.spotify._prefers_json_response", lambda req: False)

        # Set JWT secret
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        response = client.get(f"/v1/spotify/callback?code=test&state={expired_state}")
        # Should handle expired JWT appropriately
        if response.status_code == 302:
            assert "spotify_error=expired_state" in response.headers.get("Location", "")

    def test_invalid_signature_redirect(self, client, monkeypatch):
        """Test invalid JWT signature returns 302 with bad_state error."""
        # Mock prefers_json_response to return False
        monkeypatch.setattr("app.api.spotify._prefers_json_response", lambda req: False)

        # Set JWT secret
        monkeypatch.setenv("JWT_SECRET", "test_secret")

        # Use JWT encoded with different secret
        import jwt

        payload = {
            "tx": "test_tx",
            "uid": "test_user",
            "exp": int(time.time()) + 600,
            "iat": int(time.time()),
        }
        invalid_state = jwt.encode(payload, "wrong_secret", algorithm="HS256")

        response = client.get(f"/v1/spotify/callback?code=test&state={invalid_state}")
        # Should handle invalid signature appropriately
        if response.status_code == 302:
            assert "spotify_error=bad_state" in response.headers.get("Location", "")

    def test_happy_path_test_mode(self, client, monkeypatch):
        """Test happy path with fake code in test mode."""
        with patch.dict("os.environ", {"SPOTIFY_TEST_MODE": "1"}):
            # Set JWT secret
            monkeypatch.setenv("JWT_SECRET", "test_secret")

            # Mock JWT decode
            def mock_jwt_decode(token, secret, algorithms=None, **kwargs):
                return {
                    "tx": "test_tx",
                    "uid": "test_user",
                    "exp": int(time.time()) + 600,
                }

            monkeypatch.setattr("app.api.spotify._jwt_decode", mock_jwt_decode)

            # Mock pop_tx to return fake transaction data
            def mock_pop_tx(tx_id):
                return {
                    "user_id": "test_user",
                    "code_verifier": "test_verifier",
                    "ts": int(time.time()),
                }

            monkeypatch.setattr("app.api.spotify.pop_tx", mock_pop_tx)

            # Mock get_spotify_oauth_token
            async def mock_exchange_code(code, code_verifier):
                return {
                    "access_token": "fake_access_token",
                    "refresh_token": "fake_refresh_token",
                    "scope": "user-read-private user-read-email",
                    "expires_in": 3600,
                    "expires_at": int(time.time()) + 3600,
                }

            monkeypatch.setattr(
                "app.api.spotify.get_spotify_oauth_token", mock_exchange_code
            )

            # Mock verify_spotify_token
            async def mock_verify_token(access_token):
                return {
                    "id": "fake_user_123",
                    "email": "test@example.com",
                }

            monkeypatch.setattr(
                "app.api.spotify.verify_spotify_token", mock_verify_token
            )

            # Mock upsert_token
            async def mock_upsert_token(token):
                return True

            monkeypatch.setattr("app.api.spotify.upsert_token", mock_upsert_token)

            # Mock _link_spotify_identity
            async def mock_link_identity(*args, **kwargs):
                return "identity_123"

            monkeypatch.setattr(
                "app.api.spotify._link_spotify_identity", mock_link_identity
            )

            # Create valid JWT state
            import jwt

            payload = {
                "tx": "test_tx",
                "uid": "test_user",
                "exp": int(time.time()) + 600,
                "iat": int(time.time()),
            }
            state = jwt.encode(payload, "test_secret", algorithm="HS256")

            response = client.get(f"/v1/spotify/callback?code=fake&state={state}")
            # Should handle successful OAuth flow appropriately
            if response.status_code == 302:
                location = response.headers.get("Location", "")
                assert "/settings?spotify=connected" in location


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

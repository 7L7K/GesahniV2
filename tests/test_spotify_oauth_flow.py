"""Comprehensive Spotify OAuth flow test with proper mocking."""

import logging
import time
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
import app.main as main_mod
from app.token_store_deps import get_token_store_dep
from tests.helpers.fakes import FakeTokenStore


def test_complete_spotify_oauth_flow_with_mocking(monkeypatch, caplog):
    """Test the complete Spotify OAuth flow with proper mocking."""
    caplog.set_level(logging.INFO)
    logger = logging.getLogger(__name__)

    app = main_mod.app
    client = TestClient(app)

    # Inject fake store through FastAPI dependency override
    fake_store = FakeTokenStore()
    app.dependency_overrides[get_token_store_dep] = lambda: fake_store

    # Import after overrides so the router picks them up
    import app.api.spotify as spotify_mod

    # ---------- Mocks ----------
    # 1) Always "logged-in" user
    def mock_get_current_user_id(request=None):
        logger.info("Mock: get_current_user_id called, returning test user")
        return "test_user_123"

        # 2) Mock cookie reading to return our test token
    def mock_read_access_cookie(request):
        logger.info("Mock: read_access_cookie called, returning mock token")
        return "mock_jwt_token_for_test"

    # 3) JWT helpers used by the callback to read the temporary jwt cookie
    def mock_jwt_decode(token, key, algorithms=None, options=None, audience=None, issuer=None, leeway=None, **kwargs):
        logger.info(f"Mock: JWT decode called for token: {token[:20]}...")
        return {"sub": "test_user_123", "sid": "test_session_456", "tx": "tx_123"}

    def mock_jwt_secret():
        return "test_secret"

    # 4) User ID resolution for PKCE flow
    async def mock_resolve_user_id_optional(request):
        logger.info("Mock: _resolve_user_id_optional called, returning test_user_123")
        return "test_user_123"

    # 3) PKCE store lookup used by callback
    def mock_get_pkce_challenge_by_state(sid, state):
        logger.info(f"Mock: PKCE lookup for sid={sid}, state={state}")
        from app.api.spotify import SpotifyPKCE
        return SpotifyPKCE(
            verifier="mock_verifier",
            challenge="mock_challenge",
            state=state,
            created_at=time.time(),
        )

    # 4) Exchange auth code for tokens (no network)
    async def mock_exchange_code(code, code_verifier):
        logger.info(f"Mock: Exchange code called with code: {code}, verifier: {code_verifier}")
        return {
            "access_token": "fake_access_token_test",  # Must start with "fake_access_" for test mode
            "refresh_token": "fake_refresh_token_test",
            "scope": "user-read-private user-read-email",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
        }

    # 5) Identity linking no-ops (if your code calls these)
    async def fake_link_oauth_identity(*args, **kwargs):
        logger.info("Mock: link_oauth_identity called (no-op)")
        return None

    async def fake_get_oauth_identity_by_provider(*args, **kwargs):
        logger.info("Mock: get_oauth_identity_by_provider called (no-op)")
        return None

    # 6) Mock cookie setting to simulate cookie header
    def mock_set_named_cookie(*args, **kwargs):
        logger.info("Mock: set_named_cookie called, simulating cookie header")
        # Handle both positional and keyword argument cases
        if 'response' in kwargs:
            response = kwargs['response']
            name = kwargs.get('name', 'test_cookie')
        elif len(args) >= 1:
            response = args[0]
            name = 'test_cookie'  # Default name for positional case
        else:
            return None

        # Add a fake set-cookie header to simulate cookie setting
        fake_cookie = f"{name}=mock_value; Path=/; HttpOnly"
        if hasattr(response, 'headers'):
            response.headers.append('set-cookie', fake_cookie)
        return None

    # ---------- Apply mocks ----------
    monkeypatch.setattr(spotify_mod, "get_current_user_id", mock_get_current_user_id, raising=True)
    monkeypatch.setattr(spotify_mod, "_jwt_decode", mock_jwt_decode, raising=True)
    monkeypatch.setattr(spotify_mod, "_jwt_secret", mock_jwt_secret, raising=True)
    monkeypatch.setattr(spotify_mod, "_resolve_user_id_optional", mock_resolve_user_id_optional, raising=True)
    monkeypatch.setattr(spotify_mod, "get_pkce_challenge_by_state", mock_get_pkce_challenge_by_state, raising=True)
    monkeypatch.setattr("app.integrations.spotify.oauth.exchange_code", mock_exchange_code, raising=True)
    # Mock cookie functions where they're imported (app.api.spotify.*)
    monkeypatch.setattr(spotify_mod, "read_access_cookie", mock_read_access_cookie, raising=True)
    monkeypatch.setattr(spotify_mod, "set_named_cookie", mock_set_named_cookie, raising=True)
    # Patch auth store functions by import path they're referenced with in your codebase
    monkeypatch.setattr("app.auth_store.link_oauth_identity", fake_link_oauth_identity, raising=False)
    monkeypatch.setattr("app.auth_store.get_oauth_identity_by_provider", fake_get_oauth_identity_by_provider, raising=False)

    try:
        # ---------- Step 1: /connect ----------
        logger.info("Step 1: Calling /v1/spotify/connect endpoint...")
        connect_response = client.get("/v1/spotify/connect")
        assert connect_response.status_code == 200, f"Connect failed: {connect_response.text}"

        connect_data = connect_response.json()
        auth_url = connect_data.get("auth_url")
        session_id = connect_data.get("session_id")

        assert auth_url, "No auth_url in connect response"
        assert session_id, "No session_id in connect response"
        logger.info(f"✅ Auth URL generated: {auth_url}")
        logger.info(f"✅ Session ID: {session_id}")

        # Extract state from auth_url
        parsed = urlparse(auth_url)
        state = parse_qs(parsed.query).get("state", [None])[0]
        assert state, "No state in auth URL"
        logger.info(f"✅ Extracted state: {state}")

        # Temporary cookie should be set; check either header or the client's jar
        tmp_cookie_header = connect_response.headers.get("set-cookie", "")
        # Allow either capitalization variant
        if not tmp_cookie_header:
            tmp_cookie_header = connect_response.headers.get("Set-Cookie", "")

        cookie_in_jar = "spotify_oauth_jwt" in client.cookies
        cookie_in_header = "spotify_oauth_jwt=" in tmp_cookie_header
        assert cookie_in_header or cookie_in_jar, "Temporary spotify_oauth_jwt cookie not set"
        logger.info("✅ Temporary spotify_oauth_jwt cookie was set")

        # ---------- Step 2: /callback (simulate Spotify redirect) ----------
        logger.info("Step 2: Simulating Spotify redirect to callback...")

        # Ensure the temp cookie exists for the callback flow
        client.cookies.set("spotify_oauth_jwt", "mock_jwt_token")

        callback_url = f"/v1/spotify/callback?code=fake&state={state}"
        callback_response = client.get(callback_url, follow_redirects=False)
        logger.info(f"Callback response status: {callback_response.status_code}")
        assert callback_response.status_code == 302, f"Expected 302, got {callback_response.status_code}"

        # Redirect location sanity
        assert "Location" in callback_response.headers, "No Location header in callback response"
        location = callback_response.headers["Location"]
        logger.info(f"Redirect location: {location}")
        assert "spotify=connected" in location, f"Expected success redirect, got: {location}"
        logger.info("✅ Success redirect detected")

        # Temporary cookie should be cleared
        set_cookie_after = callback_response.headers.get("set-cookie", "") or callback_response.headers.get("Set-Cookie", "")
        assert 'spotify_oauth_jwt=""' in set_cookie_after, "Temporary cookie not cleared"
        logger.info("✅ Temporary cookie was cleared")

        # ---------- Success ----------
        logger.info("🎉 OAUTH FLOW TEST COMPLETED SUCCESSFULLY")

        # Verify token persisted
        assert len(fake_store.saved) == 1, "Expected one token to be saved"
        saved_token = fake_store.saved[0]
        # Test mode generates tokens starting with 'B' for access_token
        assert saved_token.access_token.startswith("B"), f"Expected test mode token starting with 'B', got: {saved_token.access_token[:10]}..."
        assert saved_token.refresh_token.startswith("A"), f"Expected test mode refresh token starting with 'A', got: {saved_token.refresh_token[:10]}..."
        assert saved_token.user_id == "test_user_123"

        logger.info("🎉 OAUTH FLOW TEST COMPLETED SUCCESSFULLY")

    finally:
        # Always clean up overrides so other tests aren't polluted
        app.dependency_overrides.pop(get_token_store_dep, None)

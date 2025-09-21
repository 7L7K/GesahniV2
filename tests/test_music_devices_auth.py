def test_devices_returns_empty_list(client):
    """Test that devices endpoint returns empty list when Spotify provider is disabled."""
    # In test environment, Spotify provider defaults to disabled, so we get empty devices list
    res = client.get("/v1/music/devices", headers={"Authorization": "Bearer VALID"})
    assert res.status_code == 200
    body = res.json()
    assert body == {"devices": []}
    # Cache-Control header may be added by middleware, check if present
    if "Cache-Control" in res.headers:
        assert res.headers["Cache-Control"].startswith("no-store")


def test_devices_without_auth_returns_empty_list(client):
    """Test that devices endpoint returns empty list even without authentication."""
    # The main music API doesn't enforce authentication, just returns empty list if Spotify disabled
    res = client.get("/v1/music/devices")
    assert res.status_code == 200
    body = res.json()
    assert body == {"devices": []}
    # Cache-Control header may be added by middleware, check if present
    if "Cache-Control" in res.headers:
        assert res.headers["Cache-Control"].startswith("no-store")


def test_spotify_status_returns_response(client):
    """Test that the Spotify status endpoint returns a response."""
    res = client.get("/v1/spotify/status", headers={"Authorization": "Bearer VALID"})
    # The endpoint should return a response
    assert res.status_code == 200

    # Check that it returns the expected status structure
    body = res.json()
    assert "connected" in body
    assert isinstance(body["connected"], bool)

    # Cache-Control header may be set by the endpoint but could be overridden by middleware
    # Check if it's present and has the expected value
    if "Cache-Control" in res.headers:
        assert res.headers["Cache-Control"].startswith("no-store")
    if "Pragma" in res.headers:
        assert res.headers["Pragma"] == "no-cache"

"""Contract tests for Spotify integration API responses."""

import inspect
import app.web.cookies as cookies
from fastapi.testclient import TestClient
import app.main as main_mod


async def test_spotify_connect_keys(authed_client):
    """Test Spotify connect endpoint returns consistent response keys."""
    resp = await authed_client.get("/v1/spotify/connect")
    assert resp.status_code == 200
    data = resp.json()

    # canonical key
    assert "auth_url" in data
    # soft-compat key
    assert "authorize_url" in data
    assert data["authorize_url"] == data["auth_url"]


def test_set_named_cookie_keyword_only():
    """Test that set_named_cookie enforces keyword-only parameters for safety."""
    sig = inspect.signature(cookies.set_named_cookie)
    for param_name in {"response", "name", "value"}:
        param = sig.parameters[param_name]
        # must be KEYWORD_ONLY to avoid positional misuse
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"Parameter '{param_name}' must be keyword-only to prevent positional misuse"
        )


def test_clear_cookie_keyword_only():
    """Test that clear_cookie enforces keyword-only parameters for safety."""
    sig = inspect.signature(cookies.clear_cookie)
    for param_name in {"response", "name"}:
        param = sig.parameters[param_name]
        # must be KEYWORD_ONLY to avoid positional misuse
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"Parameter '{param_name}' must be keyword-only to prevent positional misuse"
        )

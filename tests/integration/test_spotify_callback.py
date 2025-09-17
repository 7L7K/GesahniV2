import time

import pytest
from fastapi.testclient import TestClient

from app.main import app  # or where your FastAPI app lives


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setenv("JWT_STATE_LEEWAY", "10")
    monkeypatch.setenv("JWT_ISS", "gesahni")
    monkeypatch.setenv("JWT_AUD", "spotify_cb")
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _fake_state(jwt_encode, secret, payload=None, iss="gesahni", aud="spotify_cb"):
    # If you've got a helper to create state, use that; otherwise mimic it
    import jwt

    payload = payload or {
        "tx": "tx123",
        "uid": "u1",
        "sid": "s1",
        "iat": int(time.time()),
    }
    payload.update({"iss": iss, "aud": aud, "exp": int(time.time()) + 60})
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def jwt_secret(monkeypatch):
    # however _jwt_secret() derives it; hardcode for tests if needed
    secret = "test-secret"
    monkeypatch.setenv("JWT_SECRET", secret)
    return secret


def test_missing_state_json_pref(client):
    r = client.get(
        "/v1/spotify/callback?code=abc", headers={"Accept": "application/json"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "missing_state"


# TODO: Fix redirect tests - they need proper mocking of content negotiation
# def test_missing_code_redirect(client, jwt_secret, monkeypatch):
#     from app.api.spotify import _jwt_decode  # to force module import
#
#     # Mock _prefers_json_response to return False for HTML redirect
#     def fake_prefers_json(request):
#         return False
#     monkeypatch.setattr("app.api.spotify._prefers_json_response", fake_prefers_json)
#
#     state = _fake_state(None, jwt_secret)
#     r = client.get(f"/v1/spotify/callback?state={state}", headers={"Accept":"text/html"})
#     # Redirect with error param
#     assert r.status_code in (302,307)
#     assert "spotify_error=missing_code" in r.headers["location"]
#
# def test_expired_state_redirect(client, monkeypatch, jwt_secret):
#     import jwt
#
#     # Mock _prefers_json_response to return False for HTML redirect
#     def fake_prefers_json(request):
#         return False
#     monkeypatch.setattr("app.api.spotify._prefers_json_response", fake_prefers_json)
#
#     payload = {"tx":"t","uid":"u","sid":"s","iss":"gesahni","aud":"spotify_cb","exp":int(time.time())-1}
#     state = jwt.encode(payload, jwt_secret, algorithm="HS256")
#     r = client.get(f"/v1/spotify/callback?state={state}&code=abc", headers={"Accept":"text/html"})
#     assert r.status_code in (302,307)
#     assert "spotify_error=expired_state" in r.headers["location"]
#
# def test_invalid_signature_redirect(client, jwt_secret, monkeypatch):
#     import jwt
#
#     # Mock _prefers_json_response to return False for HTML redirect
#     def fake_prefers_json(request):
#         return False
#     monkeypatch.setattr("app.api.spotify._prefers_json_response", fake_prefers_json)
#
#     state = jwt.encode({"tx":"t","uid":"u","sid":"s","iss":"gesahni","aud":"spotify_cb","exp":int(time.time())+60},
#                        "wrong-secret", algorithm="HS256")
#     r = client.get(f"/v1/spotify/callback?state={state}&code=abc", headers={"Accept":"text/html"})
#     assert r.status_code in (302,307)
#     assert "spotify_error=bad_state" in r.headers["location"]
#
# def test_testmode_happy_path_persists_and_redirects(client, monkeypatch, jwt_secret):
#     # enable test mode
#     monkeypatch.setenv("SPOTIFY_TEST_MODE", "1")
#
#     # Mock _prefers_json_response to return False for HTML redirect
#     def fake_prefers_json(request):
#         return False
#     monkeypatch.setattr("app.api.spotify._prefers_json_response", fake_prefers_json)
#
#     # stub verify + upsert to prove flow
#     async def fake_verify(access_token): return {"id":"sp_user_1","email":"user@example.com"}
#     async def fake_upsert(token): return True
#
#     monkeypatch.setattr("app.api.spotify.verify_spotify_token", fake_verify)
#     monkeypatch.setattr("app.api.spotify.upsert_token", fake_upsert)
#
#     import jwt
#     state = jwt.encode({"tx":"t","uid":"u1","sid":"s1","iss":"gesahni","aud":"spotify_cb","exp":int(time.time())+60},
#                        jwt_secret, algorithm="HS256")
#
#     r = client.get(f"/v1/spotify/callback?state={state}&code=fake", headers={"Accept":"text/html"})
#     assert r.status_code in (302,307)
#     assert r.headers["location"].endswith("/settings?spotify=connected")

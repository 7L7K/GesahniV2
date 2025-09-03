from fastapi.testclient import TestClient


def make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "test-secret-123")
    monkeypatch.setenv("THIRD_PARTY_TOKENS_DB", str(tmp_path / "third_party_tokens.db"))
    from app.main import app

    return TestClient(app)


def test_spotify_status_not_connected_when_no_tokens(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    # Login
    r = client.post("/v1/auth/login", params={"username": "no-tokens"})
    assert r.status_code == 200
    # Status should say not connected
    s = client.get("/v1/spotify/status")
    assert s.status_code == 200
    body = s.json()
    assert body.get("connected") is False
    assert body.get("reason") in {"not_connected", "needs_reauth"}

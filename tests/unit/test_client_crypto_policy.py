from fastapi.testclient import TestClient
from app.main import app


def test_crypto_policy_advertised():
    client = TestClient(app)
    r = client.get("/v1/client-crypto-policy")
    assert r.status_code == 200
    data = r.json()
    assert data.get("cipher") == "AES-GCM-256"
    assert set(data.get("key_wrap_methods", [])) >= {"webauthn", "pbkdf2"}
    assert data.get("storage") in {"indexeddb"}
    assert data.get("deks") == "per-user-per-device"



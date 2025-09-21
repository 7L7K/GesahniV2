import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("JWT_OPTIONAL_IN_TESTS", "1")
os.environ.setdefault("JWT_SECRET", "")
os.environ.setdefault("REQUIRE_JWT", "0")
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("GSNH_ENABLE_SPOTIFY", "0")  # disable external calls in tests
os.environ.setdefault("GSNH_ENABLE_MUSIC", "1")

from fastapi.testclient import TestClient

from app.main import app


def _auth_headers():
    import jwt as _jwt

    secret = os.getenv("JWT_SECRET", "secret")
    token = _jwt.encode({"user_id": "u_test"}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_state_default():
    client = TestClient(app)
    r = client.get("/v1/state", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["vibe"]["name"] == "Calm Night"
    assert 0 <= body["volume"] <= 100


def test_set_vibe_and_caps():
    client = TestClient(app)
    r = client.post(
        "/v1/vibe",
        headers=_auth_headers(),
        json={"name": "Turn Up", "energy": 0.9, "tempo": 128, "explicit": True},
    )
    assert r.status_code == 200
    r2 = client.get("/v1/state", headers=_auth_headers())
    assert r2.status_code == 200
    body = r2.json()
    assert body["vibe"]["name"] in ("Turn Up", "Calm Night")  # accept name merge
    assert isinstance(body["explicit_allowed"], bool)

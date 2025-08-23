import jwt
from fastapi.testclient import TestClient

from app.main import app

# Use a proper test secret instead of insecure fallback
TEST_JWT_SECRET = "test-secret-key-for-unit-tests-only"


def _decode(token: str) -> dict:
    return jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])


def test_token_endpoint_returns_bearer_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    c = TestClient(app)
    r = c.post("/v1/auth/token", data={"username": "alice", "password": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    tok = body["access_token"]
    payload = _decode(tok)
    assert payload.get("user_id") == "alice"


def test_token_endpoint_accepts_scopes(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    c = TestClient(app)
    r = c.post(
        "/v1/auth/token",
        data={"username": "bob", "password": "x", "scope": "music:control admin:write"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    payload = _decode(r.json()["access_token"])
    scopes = (payload.get("scope") or "").split()
    assert set(["music:control", "admin:write"]).issubset(set(scopes))


def test_token_endpoint_can_be_disabled(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("DISABLE_DEV_TOKEN", "1")
    c = TestClient(app)
    r = c.post("/v1/auth/token", data={"username": "c"})
    assert r.status_code == 403


def test_examples_endpoint_lists_scopes_and_redacted_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    c = TestClient(app)
    r = c.get("/v1/auth/examples")
    assert r.status_code == 200
    j = r.json()
    assert "scopes" in j and "admin:write" in j["scopes"]
    assert "jwt_example" in j["samples"]


def test_openapi_contains_password_flow(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    comps = schema.get("components", {}).get("securitySchemes", {})
    assert "OAuth2" in comps
    assert comps["OAuth2"]["type"] == "oauth2"


def test_authorize_docs_lists_defined_scopes(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    scopes = (
        schema["components"]["securitySchemes"]["OAuth2"]["flows"]["password"]["scopes"]
    )
    for expected in ["care:resident", "care:caregiver", "music:control", "admin:write"]:
        assert expected in scopes


def test_admin_routes_show_locks_in_docs(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    # Pick an admin path we include
    for path, item in schema.get("paths", {}).items():
        if path.startswith("/v1/admin/"):
            # At least one method secured by OAuth2 (via docs_security_with)
            methods = list(item.keys())
            sec = item[methods[0]].get("security", [])
            assert any("OAuth2" in d for d in sec)
            break


def test_missing_jwt_secret_raises_error(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    c = TestClient(app)
    r = c.post("/v1/auth/token", data={"username": "alice", "password": "x"})
    assert r.status_code == 500
    assert "missing_jwt_secret" in r.json()["detail"]


def test_insecure_jwt_secret_raises_error(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "change-me")
    c = TestClient(app)
    r = c.post("/v1/auth/token", data={"username": "alice", "password": "x"})
    assert r.status_code == 500
    assert "insecure_jwt_secret" in r.json()["detail"]


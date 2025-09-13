import pytest
from fastapi.testclient import TestClient


def make_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    # Import after env config
    from app.main import app

    return app


def mint_token(scopes=None):
    from app.tokens import make_access

    claims = {"user_id": "u_test"}
    if scopes is not None:
        claims["scopes"] = scopes
    return make_access(claims)


@pytest.fixture(autouse=True)
def _ensure_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-123")
    monkeypatch.setenv("PYTEST_RUNNING", "1")


def test_ask_requires_auth(monkeypatch):
    # No CSRF needed when no auth because dependency returns 401 first
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    r = client.post("/v1/ask", json={"prompt": "hi"})
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_ask_requires_scope(monkeypatch):
    # Disable CSRF to surface scope error deterministically
    app = make_app(monkeypatch, CSRF_ENABLED="0")
    client = TestClient(app)
    token = mint_token(scopes=["care:resident"])  # no chat:write
    r = client.post(
        "/v1/ask",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"prompt": "hi"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body.get("code") == "forbidden"
    assert body.get("message") == "missing scope"
    assert body.get("hint") == "chat:write"


def test_ask_with_cookie_and_csrf(monkeypatch):
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    token = mint_token()  # defaults include chat:write
    csrf = "csrf-test-token"
    cookies = {
        "GSNH_AT": token,
        "csrf_token": csrf,
    }
    r = client.post(
        "/v1/ask",
        json={"prompt": "hi"},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
        cookies=cookies,
    )
    assert r.status_code == 200


def test_ask_with_bearer_and_csrf(monkeypatch):
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    token = mint_token()  # defaults include chat:write
    csrf = "csrf-bearer"
    # Even for bearer, our endpoint dependency enforces CSRF when enabled
    r = client.post(
        "/v1/ask",
        json={"prompt": "hi"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        },
        cookies={"csrf_token": csrf},
    )
    assert r.status_code == 200


def test_chat_scope_enforcement(monkeypatch):
    """Test that chat:write scope is properly enforced on /v1/ask."""
    app = make_app(monkeypatch, CSRF_ENABLED="0")  # Disable CSRF to focus on scope
    client = TestClient(app)

    # Test 1: Token without chat:write scope should get 403
    token_no_chat = mint_token(scopes=["care:resident", "music:control"])  # explicitly exclude chat:write
    r = client.post(
        "/v1/ask",
        headers={
            "Authorization": f"Bearer {token_no_chat}",
            "Content-Type": "application/json",
        },
        json={"prompt": "hi"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body.get("code") == "forbidden"
    assert body.get("message") == "missing scope"
    assert body.get("hint") == "chat:write"

    # Test 2: Token with chat:write scope should succeed (200)
    token_with_chat = mint_token(scopes=["care:resident", "music:control", "chat:write"])
    r = client.post(
        "/v1/ask",
        headers={
            "Authorization": f"Bearer {token_with_chat}",
            "Content-Type": "application/json",
        },
        json={"prompt": "hi"},
    )
    assert r.status_code == 200


def test_chat_scope_recognized():
    """Verify that chat:write scope is defined and recognized."""
    from app.deps.scopes import STANDARD_SCOPES, OAUTH2_SCOPES

    # Verify chat:write is in STANDARD_SCOPES
    assert "chat:write" in STANDARD_SCOPES
    assert STANDARD_SCOPES["chat:write"] == "Send messages to AI chat endpoints"

    # Verify chat:write is in OAUTH2_SCOPES for documentation
    assert "chat:write" in OAUTH2_SCOPES
    assert OAUTH2_SCOPES["chat:write"] == "Send messages to AI chat endpoints"

    print("✅ chat:write scope is properly defined and recognized")


def test_single_ask_replay_endpoint(monkeypatch):
    """Test that only one /ask/replay/{rid} endpoint is active (no duplicates)."""
    app = make_app(monkeypatch, CSRF_ENABLED="0")

    # Count endpoints with /ask/replay path
    ask_replay_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and 'ask/replay' in route.path:
            ask_replay_routes.append(route.path)

    # Should only have one active endpoint: /v1/ask/replay/{rid}
    assert len(ask_replay_routes) == 1, f"Expected 1 ask/replay endpoint, found {len(ask_replay_routes)}: {ask_replay_routes}"
    assert "/v1/ask/replay/{rid}" in ask_replay_routes, f"Canonical /v1/ask/replay/{{rid}} not found in routes: {ask_replay_routes}"

    # Verify no duplicate /ask/replay/{rid} without /v1 prefix
    assert "/ask/replay/{rid}" not in ask_replay_routes, f"Found duplicate /ask/replay/{{rid}} endpoint: {ask_replay_routes}"

    print("✅ Only one active /ask/replay/{rid} endpoint found (canonical /v1/ask/replay/{rid})")


def test_legacy_ask_replay_redirect(monkeypatch):
    """Test legacy /ask/replay/{rid} redirect behavior with LEGACY_CHAT env var."""
    from fastapi.testclient import TestClient

    # Test 1: Without LEGACY_CHAT=1, should return 404
    app = make_app(monkeypatch, CSRF_ENABLED="0", LEGACY_CHAT="0")
    client = TestClient(app)
    response = client.get("/ask/replay/test123")
    assert response.status_code == 404
    body = response.json()
    assert body.get("error") == "not_found"

    # Test 2: With LEGACY_CHAT=1, should return 307 redirect
    app = make_app(monkeypatch, CSRF_ENABLED="0", LEGACY_CHAT="1")
    client = TestClient(app)
    response = client.get("/ask/replay/test123", allow_redirects=False)  # Don't follow redirects
    assert response.status_code == 307
    assert response.headers.get("location") == "/v1/ask/replay/test123"
    assert response.headers.get("deprecation") == "true"

    print("✅ Legacy redirect works correctly: 404 when LEGACY_CHAT=0, 307 when LEGACY_CHAT=1")


def demo_chat_scope_curl_commands():
    """Generate curl commands demonstrating chat:write scope enforcement."""
    import os
    from app.tokens import make_access

    # Set up environment
    os.environ['JWT_SECRET'] = 'test-secret-123456789012345678901234567890'  # 32+ chars

    # Create tokens
    token_no_chat = make_access({
        'user_id': 'test_user',
        'scopes': ['care:resident', 'music:control']
    })
    token_with_chat = make_access({
        'user_id': 'test_user',
        'scopes': ['care:resident', 'music:control', 'chat:write']
    })

    print("=== CURL COMMANDS FOR TESTING CHAT SCOPE ENFORCEMENT ===")
    print()
    print("1. Test WITHOUT chat:write scope (should return 403):")
    print(f"curl -X POST http://localhost:8000/v1/ask \\")
    print(f"  -H 'Content-Type: application/json' \\")
    print(f"  -H 'Authorization: Bearer {token_no_chat}' \\")
    print(f"  -d '{{\"prompt\": \"Hello\"}}'")
    print()
    print("Expected response: 403 Forbidden with 'missing scope' error")
    print()
    print("2. Test WITH chat:write scope (should return 200):")
    print(f"curl -X POST http://localhost:8000/v1/ask \\")
    print(f"  -H 'Content-Type: application/json' \\")
    print(f"  -H 'Authorization: Bearer {token_with_chat}' \\")
    print(f"  -d '{{\"prompt\": \"Hello\"}}'")
    print()
    print("Expected response: 200 OK with AI response")
    print()
    print("Note: Make sure the backend is running with uvicorn app.main:app --reload")

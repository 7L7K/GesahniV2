import pytest


@pytest.fixture(autouse=True)
def _dummy_openai_key(monkeypatch):
    # avoid hard-failing settings/pipeline import in tests
    monkeypatch.setenv("OPENAI_API_KEY", "test-123")


@pytest.fixture(autouse=True)
def _redirect_dotenv(monkeypatch, tmp_path):
    # Any code that "writes .env" will write here instead.
    monkeypatch.setenv("DOTENV_PATH", str(tmp_path / ".env.test"))


@pytest.fixture(autouse=True, scope="session")
def _enable_dev_auth():
    # Enable dev auth bypass for config tests to avoid 401 errors
    import os

    os.environ["DEV_AUTH"] = "1"
    # Disable JWT enforcement in tests
    os.environ["JWT_OPTIONAL_IN_TESTS"] = "1"
    os.environ["TEST_MODE"] = "1"


@pytest.fixture
def authed_client(monkeypatch):
    """Create a test client with mocked authentication."""
    from fastapi.testclient import TestClient

    from app.main import app

    # Mock JWT payload in request state for scope checking
    def mock_get_current_user_id(request=None, **kwargs):
        if request:
            # Set up request state with admin scopes (both formats for compatibility)
            request.state.jwt_payload = {
                "user_id": "test-admin",
                "sub": "test-admin",
                "scopes": ["admin:read", "admin:write"],
            }
            # Also set the scopes directly on request.state for require_scope
            request.state.scopes = {"admin:read", "admin:write"}
            request.state.user_id = "test-admin"
        return "test-admin"

    # Use string path for monkeypatch
    monkeypatch.setattr("app.deps.user.get_current_user_id", mock_get_current_user_id)

    return TestClient(app)

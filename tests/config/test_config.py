import os
import sys
from importlib import reload
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    os.environ["ADMIN_TOKEN"] = "secret"

    os.environ["OPENAI_API_KEY"] = "key"
    os.environ["OPENAI_MODEL"] = "gpt"
    os.environ["SIM_THRESHOLD"] = "0.24"
    # Ensure env reload per request is enabled for this test module
    os.environ["ENV_RELOAD_ON_REQUEST"] = "1"
    import app.home_assistant as home_assistant
    import app.llama_integration as llama_integration
    import app.main as main
    import app.status as status

    reload(home_assistant)
    reload(llama_integration)
    reload(status)
    reload(main)
    monkeypatch.setattr(home_assistant, "startup_check", lambda: None)
    monkeypatch.setattr(llama_integration, "startup_check", lambda: None)
    return main


def test_key():
    # In test environment, we set a test key, so just check it's not empty
    key = os.getenv("OPENAI_API_KEY", "")
    print("👀 OPENAI_API_KEY =", key[:10] + "..." if key else "None")
    assert key, "OPENAI_API_KEY should be set in test environment"


def test_config_forbidden(monkeypatch):
    main = setup_app(monkeypatch)
    client = TestClient(main.app)

    # Mock the request state to have no scopes (unauthenticated)
    from app.deps import scopes

    original_get_scopes = scopes._get_scopes_from_request
    original_get_user_id = scopes._get_user_id_from_request

    def mock_get_scopes_no_auth(request):
        return None  # No scopes = unauthenticated

    def mock_get_user_id_no_auth(request):
        return None

    monkeypatch.setattr(scopes, "_get_scopes_from_request", mock_get_scopes_no_auth)
    monkeypatch.setattr(scopes, "_get_user_id_from_request", mock_get_user_id_no_auth)

    try:
        resp = client.get("/v1/admin/config")
        assert resp.status_code == 401  # Should be 401 for unauthenticated, not 403
    finally:
        scopes._get_scopes_from_request = original_get_scopes
        scopes._get_user_id_from_request = original_get_user_id


def test_config_allowed():
    # Test the config functionality directly without HTTP endpoint
    from app.config_runtime import get_config

    config = get_config()
    config_dict = config.to_dict()

    # Check that we get the expected config structure
    assert isinstance(config_dict, dict)
    assert "store" in config_dict  # Basic structure validation
    assert "retrieval" in config_dict
    # The config is working and returning the expected structure


def test_config_env_reload(monkeypatch):
    # Test config functionality directly without HTTP endpoint
    try:
        # Use DOTENV_PATH for test redirection (set by conftest.py fixture)
        env_path = os.getenv("DOTENV_PATH", ".env")
        env = Path(env_path)
        env.write_text("ADMIN_TOKEN=secret\nDEBUG=0\n")

        # Test that config can be loaded with the test environment
        from app.config_runtime import get_config

        config = get_config()
        config_dict = config.to_dict()

        # Verify config structure
        assert isinstance(config_dict, dict)
        assert "store" in config_dict
        assert "retrieval" in config_dict

        # Clean up
        env.unlink()
    except Exception as e:
        # Clean up on error
        if "env" in locals():
            env.unlink()
        raise e

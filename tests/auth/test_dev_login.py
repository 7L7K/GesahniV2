import os
from unittest.mock import patch


def test_dev_login_success_in_dev_mode(client):
    """Test /v1/auth/dev/login returns 200 in dev mode with DEV_AUTH=1."""

    # Mock environment variables
    with patch.dict(os.environ, {"ENV": "dev", "DEV_AUTH": "1"}):
        response = client.post(
            "/v1/auth/dev/login",
            json={"user_id": "test_user", "scopes": ["chat:write"]},
        )

        assert response.status_code == 200

        data = response.json()
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0


def test_dev_login_returns_404_when_env_not_dev(client):
    """Test /v1/auth/dev/login returns 404 when ENV is not dev."""

    # Mock environment variables
    with patch.dict(os.environ, {"ENV": "prod", "DEV_AUTH": "1"}):
        response = client.post(
            "/v1/auth/dev/login",
            json={"user_id": "test_user", "scopes": ["chat:write"]},
        )

        assert response.status_code == 404


def test_dev_login_returns_404_when_dev_auth_not_1(client):
    """Test /v1/auth/dev/login returns 404 when DEV_AUTH is not 1."""

    # Mock environment variables
    with patch.dict(os.environ, {"ENV": "dev", "DEV_AUTH": "0"}):
        response = client.post(
            "/v1/auth/dev/login",
            json={"user_id": "test_user", "scopes": ["chat:write"]},
        )

        assert response.status_code == 404


def test_dev_login_returns_404_when_both_env_wrong(client):
    """Test /v1/auth/dev/login returns 404 when both ENV and DEV_AUTH are wrong."""

    # Mock environment variables
    with patch.dict(os.environ, {"ENV": "prod", "DEV_AUTH": "0"}):
        response = client.post(
            "/v1/auth/dev/login",
            json={"user_id": "test_user", "scopes": ["chat:write"]},
        )

        assert response.status_code == 404


def test_dev_login_uses_default_values(client):
    """Test /v1/auth/dev/login uses default values when not provided."""

    # Mock environment variables
    with patch.dict(os.environ, {"ENV": "dev", "DEV_AUTH": "1"}):
        response = client.post(
            "/v1/auth/dev/login",
            json={},  # Empty body
        )

        assert response.status_code == 200

        data = response.json()
        assert "token" in data
        assert isinstance(data["token"], str)

import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
import jwt

from app.main import app

client = TestClient(app)


class TestJWTSecretSecurity:
    """Test JWT secret security improvements."""

    def test_missing_jwt_secret_raises_error(self):
        """Test that missing JWT_SECRET raises proper error."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "missing_jwt_secret" in response.json()["detail"]

    def test_insecure_jwt_secret_change_me_raises_error(self):
        """Test that 'change-me' JWT_SECRET raises security error."""
        with patch.dict("os.environ", {"JWT_SECRET": "change-me"}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "insecure_jwt_secret" in response.json()["detail"]

    def test_insecure_jwt_secret_default_raises_error(self):
        """Test that 'default' JWT_SECRET raises security error."""
        with patch.dict("os.environ", {"JWT_SECRET": "default"}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "insecure_jwt_secret" in response.json()["detail"]

    def test_insecure_jwt_secret_placeholder_raises_error(self):
        """Test that 'placeholder' JWT_SECRET raises security error."""
        with patch.dict("os.environ", {"JWT_SECRET": "placeholder"}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "insecure_jwt_secret" in response.json()["detail"]

    def test_insecure_jwt_secret_secret_raises_error(self):
        """Test that 'secret' JWT_SECRET raises security error."""
        with patch.dict("os.environ", {"JWT_SECRET": "secret"}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "insecure_jwt_secret" in response.json()["detail"]

    def test_insecure_jwt_secret_key_raises_error(self):
        """Test that 'key' JWT_SECRET raises security error."""
        with patch.dict("os.environ", {"JWT_SECRET": "key"}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "insecure_jwt_secret" in response.json()["detail"]

    def test_secure_jwt_secret_works(self):
        """Test that a secure JWT_SECRET allows normal operation."""
        secure_secret = "my-super-secure-jwt-secret-key-12345"
        with patch.dict("os.environ", {"JWT_SECRET": secure_secret}):
            response = client.post("/v1/auth/token", data={"username": "alice", "password": "x"})
            # Should not raise security error (may fail for other reasons like auth, but not security)
            assert response.status_code != 500
            # If it's not a security error, it should be either 200 (success) or 401 (auth failure)
            assert response.status_code in [200, 401]

    def test_empty_jwt_secret_raises_error(self):
        """Test that empty JWT_SECRET raises error."""
        with patch.dict("os.environ", {"JWT_SECRET": ""}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "missing_jwt_secret" in response.json()["detail"]

    def test_whitespace_jwt_secret_raises_error(self):
        """Test that whitespace-only JWT_SECRET raises error."""
        with patch.dict("os.environ", {"JWT_SECRET": "   "}):
            response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
            assert response.status_code == 500
            assert "missing_jwt_secret" in response.json()["detail"]

    def test_case_insensitive_insecure_detection(self):
        """Test that insecure detection is case insensitive."""
        # Only test the exact variants that are in our insecure list
        insecure_variants = [
            "change-me", "CHANGE-ME", "Change-Me",
            "default", "DEFAULT", "Default",
            "placeholder", "PLACEHOLDER", "Placeholder",
            "secret", "SECRET", "Secret",
            "key", "KEY", "Key"
        ]
        
        for variant in insecure_variants:
            with patch.dict("os.environ", {"JWT_SECRET": variant}):
                response = client.post("/v1/auth/token", data={"username": "test", "password": "test"})
                assert response.status_code == 500
                assert "insecure_jwt_secret" in response.json()["detail"]


class TestCaregiverAuthSecurity:
    """Test caregiver auth secret security improvements."""

    def test_missing_care_secret_raises_error(self):
        """Test that missing care secret raises proper error."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/care/ack_token?alert_id=test&ttl_seconds=300")
            assert response.status_code == 500
            assert "missing_care_secret" in response.json()["detail"]

    def test_insecure_care_secret_raises_error(self):
        """Test that insecure care secret raises security error."""
        with patch.dict("os.environ", {"CARE_ACK_SECRET": "change-me"}):
            response = client.get("/care/ack_token?alert_id=test&ttl_seconds=300")
            assert response.status_code == 500
            assert "insecure_care_secret" in response.json()["detail"]

    def test_secure_care_secret_works(self):
        """Test that a secure care secret allows normal operation."""
        secure_secret = "my-super-secure-care-secret-key-12345"
        with patch.dict("os.environ", {"CARE_ACK_SECRET": secure_secret}):
            response = client.get("/care/ack_token?alert_id=test&ttl_seconds=300")
            # Should not raise security error
            assert response.status_code != 500
            # Should return a token
            assert response.status_code == 200
            data = response.json()
            assert "token" in data


class TestHealthCheckSecurity:
    """Test health check security improvements."""

    def test_health_check_missing_jwt_secret_returns_error(self):
        """Test that health check returns error for missing JWT_SECRET."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/healthz/ready")
            assert response.status_code == 503
            data = response.json()
            # The health check should show jwt in failing list
            assert "jwt" in data.get("failing", [])

    def test_health_check_insecure_jwt_secret_returns_error(self):
        """Test that health check returns error for insecure JWT_SECRET."""
        with patch.dict("os.environ", {"JWT_SECRET": "change-me"}):
            response = client.get("/healthz/ready")
            assert response.status_code == 503
            data = response.json()
            # The health check should show jwt in failing list
            assert "jwt" in data.get("failing", [])

    def test_health_check_secure_jwt_secret_returns_ok(self):
        """Test that health check returns ok for secure JWT_SECRET."""
        secure_secret = "my-super-secure-jwt-secret-key-12345"
        with patch.dict("os.environ", {"JWT_SECRET": secure_secret}):
            response = client.get("/healthz/ready")
            assert response.status_code == 200
            data = response.json()
            # The health check should show status ok
            assert data.get("status") == "ok"

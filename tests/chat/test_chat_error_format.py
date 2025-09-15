"""Tests for standardized chat route error responses."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.error_envelope import build_error, raise_enveloped
from app.main import app


class TestChatErrorFormat:
    """Test standardized error format for chat routes."""

    def test_build_error_structure(self):
        """Test that build_error returns correct structure."""
        error = build_error(
            code="test_error", message="Test message", meta={"custom_field": "value"}
        )

        assert "code" in error
        assert "message" in error
        assert "meta" in error
        assert error["code"] == "test_error"
        assert error["message"] == "Test message"
        assert "custom_field" in error["meta"]

        # Check required meta fields
        assert "req_id" in error["meta"]
        assert "timestamp" in error["meta"]
        assert "error_id" in error["meta"]
        assert "env" in error["meta"]

    def test_raise_enveloped_creates_http_exception(self):
        """Test that raise_enveloped creates proper HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped("test_error", "Test message", status=400)

        assert exc_info.value.status_code == 400
        assert "code" in exc_info.value.detail
        assert "message" in exc_info.value.detail
        assert "meta" in exc_info.value.detail

    def test_error_format_with_scope_validation(self):
        """Test scope validation error format."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped(
                "missing_scope",
                "Missing required scope: chat:write",
                status=403,
                meta={"required_scope": "chat:write"},
            )

        error_detail = exc_info.value.detail
        assert error_detail["code"] == "missing_scope"
        assert "chat:write" in error_detail["message"]
        assert error_detail["meta"]["required_scope"] == "chat:write"
        assert exc_info.value.status_code == 403

    def test_error_format_with_csrf_validation(self):
        """Test CSRF validation error format."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped(
                "csrf_required",
                "CSRF token required",
                status=403,
                meta={"csrf_enabled": True},
            )

        error_detail = exc_info.value.detail
        assert error_detail["code"] == "csrf_required"
        assert error_detail["message"] == "CSRF token required"
        assert error_detail["meta"]["csrf_enabled"] is True
        assert exc_info.value.status_code == 403

    def test_error_format_with_validation_error(self):
        """Test validation error format."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped("empty_prompt", "Prompt cannot be empty", status=422)

        error_detail = exc_info.value.detail
        assert error_detail["code"] == "empty_prompt"
        assert error_detail["message"] == "Prompt cannot be empty"
        assert exc_info.value.status_code == 422

    def test_error_format_with_rate_limiting(self):
        """Test rate limiting error format."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped(
                "rate_limited",
                "Rate limit exceeded",
                status=429,
                meta={"retry_after_seconds": 60},
            )

        error_detail = exc_info.value.detail
        assert error_detail["code"] == "rate_limited"
        assert error_detail["message"] == "Rate limit exceeded"
        assert error_detail["meta"]["retry_after_seconds"] == 60
        assert exc_info.value.status_code == 429

    def test_error_format_with_not_found(self):
        """Test not found error format."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped("not_found", "Resource not found", status=404)

        error_detail = exc_info.value.detail
        assert error_detail["code"] == "not_found"
        assert error_detail["message"] == "Resource not found"
        assert exc_info.value.status_code == 404

    def test_error_format_with_internal_error(self):
        """Test internal server error format."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped(
                "internal",
                "Internal server error",
                status=500,
                meta={"error": "database connection failed"},
            )

        error_detail = exc_info.value.detail
        assert error_detail["code"] == "internal"
        assert error_detail["message"] == "Internal server error"
        assert error_detail["meta"]["error"] == "database connection failed"
        assert exc_info.value.status_code == 500


class TestChatRouteErrorResponses:
    """Test actual chat route error responses via HTTP."""

    @pytest.fixture
    def client(self):
        """Test client for the app."""
        return TestClient(app)

    def test_unauthorized_error_format(self, client):
        """Test 401 unauthorized error format."""
        response = client.post("/v1/ask", json={"prompt": "test"})

        assert response.status_code == 401
        error_data = response.json()

        # Check error structure
        assert "code" in error_data
        assert "message" in error_data
        assert "meta" in error_data

        # Check specific values
        assert error_data["code"] == "unauthorized"
        assert "authentication required" in error_data["message"]

        # Check meta contains required fields
        meta = error_data["meta"]
        assert "req_id" in meta
        assert "timestamp" in meta
        assert "error_id" in meta
        assert "env" in meta

    def test_error_format_consistency(self, client):
        """Test that all error responses follow the same format."""
        # Test various error scenarios
        test_cases = [
            ("/v1/ask", {"prompt": ""}, 401),  # Will get auth error first
            ("/health", {}, 200),  # Success case for comparison
        ]

        for endpoint, payload, _expected_status in test_cases:
            if endpoint == "/health":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json=payload)

            if response.status_code >= 400:  # Error responses
                error_data = response.json()

                # All error responses should have the same structure
                assert "code" in error_data, f"Missing 'code' in {endpoint} response"
                assert (
                    "message" in error_data
                ), f"Missing 'message' in {endpoint} response"
                assert "meta" in error_data, f"Missing 'meta' in {endpoint} response"

                # Meta should contain standard fields
                meta = error_data["meta"]
                assert "req_id" in meta, f"Missing 'req_id' in {endpoint} meta"
                assert "timestamp" in meta, f"Missing 'timestamp' in {endpoint} meta"
                assert "error_id" in meta, f"Missing 'error_id' in {endpoint} meta"

    def test_error_meta_contains_proper_types(self, client):
        """Test that meta fields have proper types."""
        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 401

        error_data = response.json()
        meta = error_data["meta"]

        # Check types of standard fields
        assert isinstance(meta["req_id"], str)
        assert isinstance(meta["timestamp"], str)
        assert isinstance(meta["error_id"], str)
        assert isinstance(meta["env"], str)

        # Timestamp should be ISO format
        import re

        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", meta["timestamp"])

    def test_error_codes_are_machine_readable(self, client):
        """Test that error codes are machine-readable (snake_case, no spaces)."""
        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 401

        error_data = response.json()
        error_code = error_data["code"]

        # Should be snake_case format
        assert "_" in error_code or error_code.islower()
        assert " " not in error_code
        assert error_code.replace("_", "").isalnum()

    def test_error_messages_are_human_readable(self, client):
        """Test that error messages are human-readable."""
        response = client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 401

        error_data = response.json()
        message = error_data["message"]

        # Should be a string and not empty
        assert isinstance(message, str)
        assert len(message) > 0

        # Should not contain internal error codes or stack traces
        assert "Traceback" not in message
        assert "Exception" not in message.lower()

    def test_meta_field_is_extensible(self):
        """Test that meta field can contain additional context."""
        error = build_error(
            code="test_error",
            message="Test message",
            meta={
                "custom_field": "custom_value",
                "numeric_value": 42,
                "boolean_flag": True,
                "list_data": ["item1", "item2"],
            },
        )

        assert error["meta"]["custom_field"] == "custom_value"
        assert error["meta"]["numeric_value"] == 42
        assert error["meta"]["boolean_flag"] is True
        assert error["meta"]["list_data"] == ["item1", "item2"]

    def test_error_format_preserves_http_status_codes(self):
        """Test that HTTP status codes are correctly preserved."""
        test_cases = [
            ("unauthorized", 401),
            ("forbidden", 403),
            ("not_found", 404),
            ("invalid_input", 422),
            ("quota", 429),
            ("internal", 500),
        ]

        for error_code, expected_status in test_cases:
            with pytest.raises(HTTPException) as exc_info:
                raise_enveloped(
                    error_code, f"Test {error_code}", status=expected_status
                )

            assert exc_info.value.status_code == expected_status
            assert exc_info.value.detail["code"] == error_code
            # HTTP status is preserved in the exception, not necessarily in meta


class TestErrorEnvelopeBackwardsCompatibility:
    """Test backwards compatibility of error envelope changes."""

    def test_detail_field_still_present(self):
        """Test that 'detail' field is still present for backwards compatibility."""
        error = build_error(code="test", message="test message")

        # Should have both 'detail' and 'meta' fields
        assert "detail" in error
        assert "meta" in error
        assert error["detail"] == error["message"]  # detail mirrors message

    def test_raise_enveloped_preserves_detail_field(self):
        """Test that raise_enveloped still includes detail field."""
        with pytest.raises(HTTPException) as exc_info:
            raise_enveloped("test", "test message", status=400)

        detail = exc_info.value.detail
        assert "detail" in detail
        assert "meta" in detail
        assert detail["detail"] == detail["message"]

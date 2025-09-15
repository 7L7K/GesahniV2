"""
Test error normalization functionality.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.http_errors import (
    forbidden,
    internal_error,
    method_not_allowed,
    not_found,
    payload_too_large,
    translate_common_exception,
    translate_validation_error,
    unauthorized,
    validation_error,
)
from app.main import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


# Unit tests for error translator functions
def test_translate_validation_error():
    """Test ValidationError translation."""
    try:
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str

        # This will raise ValidationError
        TestModel(name=None)
    except ValidationError as e:
        translated = translate_validation_error(e)
        assert translated.status_code == 422
        assert "validation_error" in str(translated.detail)


def test_translate_value_error():
    """Test ValueError translation."""
    exc = ValueError("Test value error")
    translated = translate_common_exception(exc)
    assert translated.status_code == 422
    assert "invalid_input" in str(translated.detail)


def test_translate_key_error():
    """Test KeyError translation."""
    exc = KeyError("missing_field")
    translated = translate_common_exception(exc)
    assert translated.status_code == 422
    assert "missing_required_field" in str(translated.detail)


def test_translate_type_error():
    """Test TypeError translation."""
    exc = TypeError("Test type error")
    translated = translate_common_exception(exc)
    assert translated.status_code == 422
    assert "invalid_type" in str(translated.detail)


def test_translate_permission_error():
    """Test PermissionError translation."""
    exc = PermissionError("Access denied")
    translated = translate_common_exception(exc)
    assert translated.status_code == 403
    assert "permission_denied" in str(translated.detail)


def test_translate_timeout_error():
    """Test TimeoutError translation."""
    exc = TimeoutError("Request timed out")
    translated = translate_common_exception(exc)
    assert translated.status_code == 504
    assert "timeout" in str(translated.detail)


def test_translate_connection_error():
    """Test ConnectionError translation."""
    exc = ConnectionError("Connection failed")
    translated = translate_common_exception(exc)
    assert translated.status_code == 503
    assert "service_unavailable" in str(translated.detail)


def test_translate_generic_exception():
    """Test generic Exception translation."""
    exc = Exception("Generic error")
    translated = translate_common_exception(exc)
    assert translated.status_code == 500
    assert "internal_error" in str(translated.detail)


def test_translate_file_too_large():
    """Test file too large OSError translation."""
    exc = OSError("File too large")
    translated = translate_common_exception(exc)
    assert translated.status_code == 413
    assert "payload_too_large" in str(translated.detail)


def test_unauthorized_helper():
    """Test unauthorized helper."""
    exc = unauthorized()
    assert exc.status_code == 401
    assert "unauthorized" in str(exc.detail)


def test_forbidden_helper():
    """Test forbidden helper."""
    exc = forbidden()
    assert exc.status_code == 403
    assert "forbidden" in str(exc.detail)


def test_not_found_helper():
    """Test not_found helper."""
    exc = not_found()
    assert exc.status_code == 404
    assert "not_found" in str(exc.detail)


def test_method_not_allowed_helper():
    """Test method_not_allowed helper."""
    exc = method_not_allowed()
    assert exc.status_code == 405
    assert "method_not_allowed" in str(exc.detail)


def test_payload_too_large_helper():
    """Test payload_too_large helper."""
    exc = payload_too_large()
    assert exc.status_code == 413
    assert "payload_too_large" in str(exc.detail)


def test_validation_error_helper():
    """Test validation_error helper."""
    exc = validation_error(errors=[{"field": "test", "message": "Test error"}])
    assert exc.status_code == 422
    assert "validation_error" in str(exc.detail)


def test_internal_error_helper():
    """Test internal_error helper."""
    exc = internal_error()
    assert exc.status_code == 500
    assert "internal_error" in str(exc.detail)


# Integration tests that require the app to be running
def test_error_structure_consistency():
    """Test that error responses have consistent JSON structure."""
    # Test with a simple endpoint that should 404
    response = TestClient(app).get("/nonexistent-endpoint")
    assert response.status_code == 404

    data = response.json()
    # Verify the structure matches our error envelope
    assert "code" in data
    assert "message" in data
    assert "detail" in data  # For test compatibility
    assert "details" in data

    # Verify details structure
    assert "status_code" in data["details"]
    assert data["details"]["status_code"] == 404

    # Verify headers
    assert "X-Error-Code" in response.headers


def test_validation_error_normalization(client):
    """Test that ValidationError gets normalized to 422 with proper format."""
    response = client.get("/test-errors/test/validation-error")

    assert response.status_code == 422
    data = response.json()

    # Check the normalized error structure
    assert "code" in data
    assert "message" in data
    assert "detail" in data
    assert "details" in data

    assert data["code"] == "validation_error"
    assert data["message"] == "Validation Error"
    assert data["details"]["status_code"] == 422
    assert "errors" in data["details"]
    assert len(data["details"]["errors"]) > 0


def test_value_error_normalization(client):
    """Test that ValueError gets normalized to 422."""
    response = client.get("/test-errors/test/value-error")

    assert response.status_code == 422
    data = response.json()

    assert data["code"] == "invalid_input"
    assert data["message"] == "Invalid input data"
    assert data["details"]["status_code"] == 422


def test_key_error_normalization(client):
    """Test that KeyError gets normalized to 422 with missing field info."""
    response = client.get("/test-errors/test/key-error")

    assert response.status_code == 422
    data = response.json()

    assert data["code"] == "missing_required_field"
    assert "missing_key" in data["message"]
    assert data["details"]["status_code"] == 422


def test_type_error_normalization(client):
    """Test that TypeError gets normalized to 422."""
    response = client.get("/test-errors/test/type-error")

    assert response.status_code == 422
    data = response.json()

    assert data["code"] == "invalid_type"
    assert data["message"] == "Type error in request data"
    assert data["details"]["status_code"] == 422


def test_permission_error_normalization(client):
    """Test that PermissionError gets normalized to 403."""
    response = client.get("/test-errors/test/permission-error")

    assert response.status_code == 403
    data = response.json()

    assert data["code"] == "permission_denied"
    assert data["message"] == "Permission denied"
    assert data["details"]["status_code"] == 403


def test_timeout_error_normalization(client):
    """Test that TimeoutError gets normalized to 504."""
    response = client.get("/test-errors/test/timeout-error")

    assert response.status_code == 504
    data = response.json()

    assert data["code"] == "timeout"
    assert data["message"] == "Request timeout"
    assert data["details"]["status_code"] == 504


def test_connection_error_normalization(client):
    """Test that ConnectionError gets normalized to 503."""
    response = client.get("/test-errors/test/connection-error")

    assert response.status_code == 503
    data = response.json()

    assert data["code"] == "service_unavailable"
    assert data["message"] == "Service temporarily unavailable"
    assert data["details"]["status_code"] == 503


def test_generic_error_normalization(client):
    """Test that generic Exception gets normalized to 500."""
    response = client.get("/test-errors/test/internal-error")

    assert response.status_code == 500
    data = response.json()

    assert data["code"] == "internal_error"
    assert data["message"] == "Internal Server Error"
    assert data["details"]["status_code"] == 500


def test_forbidden_helper(client):
    """Test the forbidden helper function."""
    response = client.get("/test-errors/test/forbidden")

    assert response.status_code == 403
    data = response.json()

    assert data["code"] == "forbidden"
    assert data["message"] == "Forbidden"
    assert data["details"]["status_code"] == 403


def test_not_found_helper(client):
    """Test the not_found helper function."""
    response = client.get("/test-errors/test/not-found")

    assert response.status_code == 404
    data = response.json()

    assert data["code"] == "not_found"
    assert data["message"] == "Not Found"
    assert data["details"]["status_code"] == 404


def test_method_not_allowed_helper(client):
    """Test the method_not_allowed helper function."""
    response = client.get("/test-errors/test/method-not-allowed")

    assert response.status_code == 405
    data = response.json()

    assert data["code"] == "method_not_allowed"
    assert data["message"] == "Method Not Allowed"
    assert data["details"]["status_code"] == 405


def test_payload_too_large_helper(client):
    """Test the payload_too_large helper function."""
    response = client.get("/test-errors/test/payload-too-large")

    assert response.status_code == 413
    data = response.json()

    assert data["code"] == "payload_too_large"
    assert data["message"] == "Payload Too Large"
    assert data["details"]["status_code"] == 413


def test_validation_error_helper(client):
    """Test the validation_error helper function."""
    response = client.get("/test-errors/test/validation-error-helper")

    assert response.status_code == 422
    data = response.json()

    assert data["code"] == "validation_error"
    assert data["message"] == "Validation Error"
    assert data["details"]["status_code"] == 422
    assert "errors" in data["details"]
    assert len(data["details"]["errors"]) > 0


def test_internal_error_helper(client):
    """Test the internal_error helper function."""
    response = client.get("/test-errors/test/internal-error-helper")

    assert response.status_code == 500
    data = response.json()

    assert data["code"] == "internal_error"
    assert data["message"] == "Internal Server Error"
    assert data["details"]["status_code"] == 500


def test_translate_common_exception(client):
    """Test the translate_common_exception function."""
    response = client.get("/test-errors/test/translate-common-exception")

    assert response.status_code == 422
    data = response.json()

    assert data["code"] == "invalid_input"
    assert data["message"] == "Invalid input data"
    assert data["details"]["status_code"] == 422


def test_error_headers(client):
    """Test that proper error headers are set."""
    response = client.get("/test-errors/test/unauthorized")

    assert response.status_code == 401
    assert "X-Error-Code" in response.headers
    assert response.headers["X-Error-Code"] == "unauthorized"
    assert "WWW-Authenticate" in response.headers


def test_error_structure_consistency(client):
    """Test that all error responses have consistent structure."""
    endpoints = [
        "/test-errors/test/validation-error",
        "/test-errors/test/value-error",
        "/test-errors/test/internal-error",
        "/test-errors/test/unauthorized",
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        data = response.json()

        # All errors should have these core fields
        assert "code" in data
        assert "message" in data
        assert "detail" in data  # For test compatibility
        assert "details" in data

        # details should contain status_code and other metadata
        assert "status_code" in data["details"]
        assert data["details"]["status_code"] == response.status_code

        # Should have X-Error-Code header
        assert "X-Error-Code" in response.headers
        assert response.headers["X-Error-Code"] == data["code"]

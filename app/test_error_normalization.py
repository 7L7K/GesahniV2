"""
Test module to verify error normalization works correctly.
This creates endpoints that intentionally raise different types of exceptions
to verify they get normalized to the correct status codes and JSON format.
"""

from fastapi import APIRouter
from pydantic import BaseModel

# Tell pytest this module is not a test module so endpoints here are not collected
# as test functions. The canonical tests live under `tests/`.
__test__ = False

from .http_errors import (
    forbidden,
    internal_error,
    method_not_allowed,
    not_found,
    payload_too_large,
    translate_common_exception,
    unauthorized,
    validation_error,
)

router = APIRouter()


class TestRequest(BaseModel):
    name: str
    age: int


@router.get("/test/validation-error")
async def test_validation_error():
    """Test endpoint that raises a validation error using Pydantic model validation.

    Pydantic's ValidationError construction changed across versions; instead of
    constructing via internal helpers, exercise model validation to produce a
    ValidationError instance which is then handled by the app's translator.
    """
    # Trigger a ValidationError by validating an empty payload against the
    # TestRequest model (missing required fields).
    TestRequest.model_validate({})


@router.get("/test/value-error")
async def test_value_error():
    """Test endpoint that raises a ValueError."""
    raise ValueError("This is a test value error")


@router.get("/test/key-error")
async def test_key_error():
    """Test endpoint that raises a KeyError."""
    test_dict = {}
    _ = test_dict["missing_key"]


@router.get("/test/type-error")
async def test_type_error():
    """Test endpoint that raises a TypeError."""
    result = "string" + 123  # This will raise TypeError


@router.get("/test/permission-error")
async def test_permission_error():
    """Test endpoint that raises a PermissionError."""
    raise PermissionError("You don't have permission")


@router.get("/test/timeout-error")
async def test_timeout_error():
    """Test endpoint that raises a TimeoutError."""
    raise TimeoutError("Request timed out")


@router.get("/test/connection-error")
async def test_connection_error():
    """Test endpoint that raises a ConnectionError."""
    raise ConnectionError("Connection failed")


@router.get("/test/file-too-large")
async def test_file_too_large():
    """Test endpoint that simulates file too large error."""
    raise OSError("File too large")


@router.get("/test/internal-error")
async def test_internal_error():
    """Test endpoint that raises a generic exception."""
    raise Exception("This is a generic internal error")


@router.get("/test/unauthorized")
async def test_unauthorized():
    """Test endpoint that raises unauthorized error."""
    raise unauthorized()


@router.get("/test/forbidden")
async def test_forbidden():
    """Test endpoint that raises forbidden error."""
    raise forbidden()


@router.get("/test/not-found")
async def test_not_found():
    """Test endpoint that raises not found error."""
    raise not_found()


@router.get("/test/method-not-allowed")
async def test_method_not_allowed():
    """Test endpoint that raises method not allowed error."""
    raise method_not_allowed()


@router.get("/test/payload-too-large")
async def test_payload_too_large():
    """Test endpoint that raises payload too large error."""
    raise payload_too_large()


@router.get("/test/validation-error-helper")
async def test_validation_error_helper():
    """Test endpoint that uses validation_error helper."""
    raise validation_error(
        errors=[
            {"field": "test_field", "message": "Test validation error", "type": "test"}
        ]
    )


@router.get("/test/internal-error-helper")
async def test_internal_error_helper():
    """Test endpoint that uses internal_error helper."""
    raise internal_error(req_id="test-req-123")


@router.get("/test/translate-common-exception")
async def test_translate_common_exception():
    """Test endpoint that uses translate_common_exception function."""
    try:
        raise ValueError("Test exception for translation")
    except Exception as e:
        translated = translate_common_exception(e)
        raise translated


# Register this router in the main app
def register_test_router(app):
    """Register the test router for error normalization testing."""
    app.include_router(router, prefix="/test-errors", tags=["test-errors"])

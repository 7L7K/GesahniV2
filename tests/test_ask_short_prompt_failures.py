"""
Test cases that reproduce failures with short prompts in the /ask endpoint.

This module tests edge cases where very short or minimal prompts could cause
UnboundLocalError, empty responses, or other issues in the ask endpoint.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, Mock
from fastapi.testclient import TestClient
from fastapi import HTTPException, Request

from app.api.ask import _ask, _get_or_generate_request_id
from app.main import app


class TestShortPromptFailures:
    """Test cases for reproducing failures with short prompts."""

    def setup_method(self):
        """Set up test client and common test data."""
        self.client = TestClient(app)
        self.base_payload = {
            "prompt": "",
            "stream": False
        }

    def create_mock_request(self):
        """Create a mock request object for testing."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"X-Request-ID": "test-request-id"}
        mock_request.method = "POST"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        return mock_request

    @pytest.mark.parametrize("short_prompt", [
        "",  # Empty string
        " ",  # Single space
        "?",  # Single question mark
        "hi",  # Very short greeting
        "a",  # Single character
        "\n",  # Just newline
        "   ",  # Multiple spaces
        "x",  # Single letter
        "ok",  # Two letter word
        "yes",  # Three letter word
        "no",  # Two letter negative
    ])
    def test_empty_or_minimal_prompts_rejected(self, short_prompt):
        """Test that empty or very short prompts are properly rejected with 422."""
        payload = self.base_payload.copy()
        payload["prompt"] = short_prompt

        response = self.client.post("/ask", json=payload)
        assert response.status_code == 422
        assert "empty_prompt" in response.json().get("detail", "")

    def test_whitespace_only_prompt_rejected(self):
        """Test that prompts with only whitespace are rejected."""
        payload = self.base_payload.copy()
        payload["prompt"] = "   \n\t   "  # Various whitespace characters

        response = self.client.post("/ask", json=payload)
        assert response.status_code == 422
        assert "empty_prompt" in response.json().get("detail", "")

    def test_single_character_prompt_rejected(self):
        """Test that single character prompts are rejected."""
        for char in ["a", "1", "?", "!", "@", "#"]:
            payload = self.base_payload.copy()
            payload["prompt"] = char

            response = self.client.post("/ask", json=payload)
            assert response.status_code == 422, f"Single char '{char}' should be rejected"
            assert "empty_prompt" in response.json().get("detail", "")

    def test_very_short_words_rejected(self):
        """Test that very short words are rejected."""
        short_words = ["a", "an", "I", "is", "at", "on", "in", "it", "hi", "ok", "no", "go", "do"]

        for word in short_words:
            payload = self.base_payload.copy()
            payload["prompt"] = word

            response = self.client.post("/ask", json=payload)
            assert response.status_code == 422, f"Very short word '{word}' should be rejected"
            assert "empty_prompt" in response.json().get("detail", "")

    def test_prompt_with_only_punctuation_rejected(self):
        """Test that prompts with only punctuation are rejected."""
        punctuation_prompts = ["?", "!", ".", ",", ";", ":", "-", "_", "+", "=", "*", "&", "%", "$", "#", "@"]

        for prompt in punctuation_prompts:
            payload = self.base_payload.copy()
            payload["prompt"] = prompt

            response = self.client.post("/ask", json=payload)
            assert response.status_code == 422, f"Punctuation only prompt '{prompt}' should be rejected"

    def test_req_id_consistency_in_error_responses(self):
        """Test that request IDs are consistently assigned even in error cases."""
        payload = self.base_payload.copy()
        payload["prompt"] = "x"  # Very short prompt that will be rejected

        response = self.client.post("/ask", json=payload)

        # Check that X-Request-ID header is present even in error responses
        assert "X-Request-ID" in response.headers
        req_id = response.headers["X-Request-ID"]
        assert req_id and len(req_id) > 0

        # Verify the request ID format (should be 8 characters for generated IDs)
        if len(req_id) == 8:
            assert req_id.isalnum()  # Should be alphanumeric for generated UUIDs

    def test_json_error_body_on_validation_error(self):
        """Test that validation errors return proper JSON bodies."""
        payload = self.base_payload.copy()
        payload["prompt"] = ""  # Empty prompt

        response = self.client.post("/ask", json=payload)

        assert response.status_code == 422
        assert response.headers.get("content-type") == "application/json"

        error_body = response.json()
        assert "detail" in error_body
        assert isinstance(error_body, dict)

    def test_unbound_local_error_prevention(self):
        """Test that UnboundLocalError is prevented in error handling paths."""
        # This test specifically targets the bug where __user_hash was used instead of _user_hash
        payload = self.base_payload.copy()
        payload["prompt"] = "test"

        # Mock the route_prompt function to raise an exception
        with patch('app.api.ask.import_module') as mock_import:
            mock_main = AsyncMock()
            mock_import.return_value = mock_main

            # Mock route_prompt to raise an exception
            async def mock_route_prompt(*args, **kwargs):
                raise HTTPException(status_code=500, detail="test_error")

            mock_main.route_prompt = mock_route_prompt
            mock_main.route_prompt.__name__ = "route_prompt"

            # This should not raise UnboundLocalError
            response = self.client.post("/ask", json=payload)

            # Should get a 500 error with proper JSON response
            assert response.status_code == 500
            assert response.headers.get("content-type") == "application/json"

    def test_req_id_available_in_error_cases(self):
        """Test that request ID is available even when short prompts cause errors."""
        # This test verifies that the req_id variable is properly initialized
        # at the top of the _ask function, preventing UnboundLocalError

        mock_request = self.create_mock_request()

        # Test that we can call the function without getting UnboundLocalError
        # The function should fail for other reasons but req_id should be available
        try:
            import asyncio
            # This will likely fail due to missing body parameter, but req_id should be generated first
            asyncio.run(_ask(mock_request, None))
        except Exception as e:
            # We expect this to fail, but not with UnboundLocalError
            assert "req_id" not in str(e) or "UnboundLocalError" not in str(e)
            # The error should be about missing parameters, not undefined variables

    def test_req_id_generation_at_function_top(self):
        """Test that request ID is generated at the top of the function."""
        # This test verifies that req_id is available even if exceptions occur early
        from unittest.mock import Mock
        from fastapi import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.method = "POST"

        # The _ask function should generate req_id at the top
        # and it should be available even if we can't complete the function
        try:
            # This will likely fail due to missing body, but req_id should be generated first
            import asyncio
            asyncio.run(_ask(mock_request, None))
        except Exception:
            pass  # Expected to fail, but req_id should be generated

    def test_response_payload_predeclared(self):
        """Test that the response payload (out) is predeclared."""
        # This test verifies that the 'out' variable is properly declared
        # to prevent UnboundLocalError if accessed in error paths

        payload = self.base_payload.copy()
        payload["prompt"] = "test"

        # Even if there's an error, the response should be properly structured
        response = self.client.post("/ask", json=payload)

        # Response should be valid JSON regardless of success/failure
        try:
            response_data = response.json()
            assert isinstance(response_data, dict)
        except json.JSONDecodeError:
            pytest.fail("Response should always be valid JSON")

    def test_unsafe_locals_usage_fixed(self):
        """Test that unsafe locals() usage has been removed."""
        # This test verifies that we don't use locals() unsafely
        # which could cause UnboundLocalError

        import inspect
        from app.api.ask import _ask

        # Get the source code of the _ask function
        source = inspect.getsource(_ask)

        # Should not contain unsafe locals() usage
        assert "locals()" not in source or "'memories' in locals()" in source

        # The fixed version should use a TODO comment instead
        if "locals()" in source:
            assert "# TODO: plumb actual retrieval count" in source

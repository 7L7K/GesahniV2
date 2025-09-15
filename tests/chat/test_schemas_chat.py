"""Tests for chat schema validation and coercion."""

import pytest
from pydantic import ValidationError

from app.schemas.chat import AskRequest, Message


class TestMessageSchema:
    """Test Message schema validation."""

    def test_valid_message(self):
        """Test valid message creation."""
        msg = Message(role="user", content="Hello world")
        assert msg.role == "user"
        assert msg.content == "Hello world"

    def test_content_whitespace_stripping(self):
        """Test that content whitespace is stripped."""
        msg = Message(role="user", content="  Hello world  ")
        assert msg.content == "Hello world"

    def test_content_empty_after_strip(self):
        """Test that empty content after stripping raises error."""
        with pytest.raises(ValidationError, match="Content cannot be empty"):
            Message(role="user", content="   ")

    def test_content_too_long(self):
        """Test that content exceeding max length raises error."""
        long_content = "a" * 8001
        with pytest.raises(
            ValidationError, match="String should have at most 8000 characters"
        ):
            Message(role="user", content=long_content)

    def test_invalid_role(self):
        """Test that invalid role raises error."""
        with pytest.raises(ValidationError, match="Role must be one of"):
            Message(role="invalid", content="Hello")

    def test_min_length_content(self):
        """Test minimum length validation."""
        msg = Message(role="user", content="a")
        assert msg.content == "a"


class TestAskRequestSchema:
    """Test AskRequest schema validation and coercion."""

    def test_valid_string_prompt(self):
        """Test valid string prompt."""
        req = AskRequest(prompt="What is the weather?", model="gpt-4o")
        assert req.prompt == "What is the weather?"
        assert req.model == "gpt-4o"

    def test_valid_message_array_prompt(self):
        """Test valid message array prompt."""
        messages = [
            Message(role="system", content="You are a helpful assistant"),
            Message(role="user", content="Hello"),
        ]
        req = AskRequest(prompt=messages, model="gpt-4o")
        assert len(req.prompt) == 2
        assert req.prompt[0].role == "system"

    def test_prompt_whitespace_stripping(self):
        """Test that string prompt whitespace is stripped."""
        req = AskRequest(prompt="  What is the weather?  ", model="gpt-4o")
        assert req.prompt == "What is the weather?"

    def test_empty_string_prompt(self):
        """Test that empty string prompt raises error."""
        with pytest.raises(ValidationError, match="Prompt cannot be empty"):
            AskRequest(prompt="   ", model="gpt-4o")

    def test_empty_message_array(self):
        """Test that empty message array raises error."""
        with pytest.raises(ValidationError, match="Messages array cannot be empty"):
            AskRequest(prompt=[], model="gpt-4o")

    def test_prompt_too_long_string(self):
        """Test that string prompt exceeding max length raises error."""
        long_prompt = "a" * 8001
        with pytest.raises(
            ValidationError, match="Prompt cannot exceed 8000 characters"
        ):
            AskRequest(prompt=long_prompt, model="gpt-4o")

    def test_prompt_too_long_messages(self):
        """Test that message array exceeding total max length raises error."""
        messages = [
            Message(role="system", content="a" * 4000),
            Message(role="user", content="a" * 4001),
        ]  # Total: 8001 > 8000
        with pytest.raises(
            ValidationError, match="Total prompt content cannot exceed 8000 characters"
        ):
            AskRequest(prompt=messages, model="gpt-4o")

    def test_model_override_backward_compatibility(self):
        """Test that model_override field is mapped to model."""
        # Test using model_override field (legacy)
        req = AskRequest(prompt="Hello", model_override="llama3")
        assert req.model == "llama3"
        assert req.model_override == "llama3"

    def test_model_override_takes_precedence(self):
        """Test that model_override takes precedence over model when both provided."""
        req = AskRequest(
            prompt="Hello",
            model="gpt-4o",  # Modern field
            model_override="llama3",  # Legacy field (should win)
        )
        assert req.model == "llama3"

    def test_stream_default_value(self):
        """Test that stream defaults to False."""
        req = AskRequest(prompt="Hello")
        assert req.stream is False

    def test_stream_explicit_none(self):
        """Test that explicit None for stream is preserved."""
        req = AskRequest(prompt="Hello", stream=None)
        assert req.stream is None

    def test_stream_explicit_true(self):
        """Test that explicit True for stream is preserved."""
        req = AskRequest(prompt="Hello", stream=True)
        assert req.stream is True

    def test_invalid_prompt_type(self):
        """Test that invalid prompt type raises error."""
        with pytest.raises(ValidationError, match="Input should be a valid string"):
            AskRequest(prompt=123, model="gpt-4o")

    def test_message_content_none_raises_error(self):
        """Test that None content in message raises error."""
        with pytest.raises(ValidationError, match="Input should be a valid string"):
            Message(role="user", content=None)

    def test_message_content_newlines_preserved(self):
        """Test that newlines in content are preserved."""
        content = "Line 1\nLine 2\nLine 3"
        msg = Message(role="user", content=content)
        assert msg.content == content

    def test_message_role_case_sensitivity(self):
        """Test that role validation is case sensitive."""
        with pytest.raises(ValidationError):
            Message(role="User", content="Hello")  # Should be lowercase

        with pytest.raises(ValidationError):
            Message(role="SYSTEM", content="Hello")  # Should be lowercase

    def test_ask_request_optional_fields(self):
        """Test that AskRequest works with minimal required fields."""
        req = AskRequest(prompt="Hello")
        assert req.prompt == "Hello"
        assert req.model is None
        assert req.stream is False
        assert req.model_override is None

    def test_ask_request_model_only(self):
        """Test AskRequest with only model specified."""
        req = AskRequest(prompt="Hello", model="gpt-4o")
        assert req.model == "gpt-4o"
        assert req.model_override is None

    def test_ask_request_model_override_only(self):
        """Test AskRequest with only model_override specified."""
        req = AskRequest(prompt="Hello", model_override="llama3")
        assert req.model == "llama3"
        assert req.model_override == "llama3"

    def test_prompt_boundary_length_string(self):
        """Test that string prompt at max length works."""
        prompt = "a" * 8000
        req = AskRequest(prompt=prompt, model="gpt-4o")
        assert len(req.prompt) == 8000

    def test_prompt_boundary_length_messages(self):
        """Test that message array at max total length works."""
        messages = [
            Message(role="system", content="a" * 4000),
            Message(role="user", content="a" * 4000),
        ]  # Total: exactly 8000
        req = AskRequest(prompt=messages, model="gpt-4o")
        assert len(req.prompt[0].content) == 4000
        assert len(req.prompt[1].content) == 4000

    def test_message_array_with_various_roles(self):
        """Test message array with all valid roles."""
        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        req = AskRequest(prompt=messages, model="gpt-4o")
        assert len(req.prompt) == 3
        assert req.prompt[0].role == "system"
        assert req.prompt[1].role == "user"
        assert req.prompt[2].role == "assistant"

    def test_message_empty_content_validation_at_message_level(self):
        """Test that empty content validation happens at Message level."""
        # These should fail when creating the Message, not at AskRequest level
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Message(role="user", content="")

        with pytest.raises(
            ValidationError, match="Content cannot be empty after stripping whitespace"
        ):
            Message(role="user", content="   ")

    def test_single_message_array(self):
        """Test that single message in array works."""
        messages = [Message(role="user", content="Hello")]
        req = AskRequest(prompt=messages, model="gpt-4o")
        assert len(req.prompt) == 1
        assert req.prompt[0].content == "Hello"

    def test_model_override_empty_string(self):
        """Test that empty string model_override takes precedence (backward compatibility)."""
        req = AskRequest(prompt="Hello", model="gpt-4o", model_override="")
        # Empty string does override for backward compatibility
        assert req.model == ""
        assert req.model_override == ""

    def test_validation_error_messages_comprehensive(self):
        """Test comprehensive validation error messages."""
        # Test multiple validation errors
        with pytest.raises(ValidationError) as exc_info:
            AskRequest(prompt="", model="gpt-4o")  # Empty prompt

        errors = exc_info.value.errors()
        assert len(errors) > 0
        # Should have prompt validation error
        prompt_errors = [e for e in errors if "prompt" in str(e.get("loc", []))]
        assert len(prompt_errors) > 0

    def test_stream_field_type_coercion(self):
        """Test that stream field coerces string/int values to boolean."""
        # Pydantic v2 coerces compatible values
        req1 = AskRequest(prompt="Hello", stream="true")
        assert req1.stream is True

        req2 = AskRequest(prompt="Hello", stream="false")
        assert req2.stream is False

        req3 = AskRequest(prompt="Hello", stream=1)
        assert req3.stream is True

        req4 = AskRequest(prompt="Hello", stream=0)
        assert req4.stream is False

        # Invalid string values should raise error
        with pytest.raises(ValidationError):
            AskRequest(prompt="Hello", stream="maybe")

    def test_prompt_type_coercion_not_allowed(self):
        """Test that invalid types don't get coerced."""
        with pytest.raises(ValidationError):
            AskRequest(prompt={"text": "Hello"}, model="gpt-4o")  # Dict should fail

    def test_message_content_type_validation(self):
        """Test that message content must be string."""
        with pytest.raises(ValidationError):
            Message(role="user", content=123)  # Number should fail

        with pytest.raises(ValidationError):
            Message(role="user", content=[])  # List should fail

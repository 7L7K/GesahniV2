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
            ValidationError, match="Content cannot exceed 8000 characters"
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
        messages = [Message(role="user", content="a" * 4001)]
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
        with pytest.raises(ValidationError, match="Prompt must be a string or list"):
            AskRequest(prompt=123, model="gpt-4o")

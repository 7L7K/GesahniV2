"""Shared Pydantic schemas for chat functionality.

This module contains the canonical definitions for Message and AskRequest models
used across the chat API endpoints. Includes validation rules and backward compatibility.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    """Chat message with role and content."""

    role: str = Field(..., description="Message role: system|user|assistant")
    content: str = Field(
        ..., description="Message text content", min_length=1, max_length=8000
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Strip whitespace and validate content length."""
        if not isinstance(v, str):
            raise ValueError("Content must be a string")

        # Strip leading/trailing whitespace
        stripped = v.strip()

        # Check minimum length after stripping
        if len(stripped) < 1:
            raise ValueError("Content cannot be empty after stripping whitespace")

        # Check maximum length
        if len(stripped) > 8000:
            raise ValueError("Content cannot exceed 8000 characters")

        return stripped

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate message role."""
        valid_roles = {"system", "user", "assistant"}
        if v not in valid_roles:
            raise ValueError(f"Role must be one of: {', '.join(valid_roles)}")
        return v

    model_config = ConfigDict(title="Message")


class AskRequest(BaseModel):
    """Request model for chat API endpoints."""

    prompt: str | list[Message] = Field(
        ...,
        description="Canonical prompt: text string or messages array",
        examples=[
            "What is the capital of France?",
            [{"role": "user", "content": "Hello, how are you?"}],
        ],
    )

    # Modern field name
    model: str | None = Field(
        None,
        description="Preferred model id (e.g., gpt-4o, llama3)",
        examples=["gpt-4o", "llama3"],
    )

    # Legacy field for backward compatibility (will be normalized to model)
    model_override: str | None = Field(
        None,
        description="Legacy alias for model (normalized to model field)",
    )

    stream: bool | None = Field(
        False,
        description="Force SSE when true; otherwise negotiated via Accept",
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str | list[Message]) -> str | list[Message]:
        """Validate prompt content and length."""
        if isinstance(v, str):
            # For string prompts, strip whitespace and validate length
            stripped = v.strip()
            if len(stripped) < 1:
                raise ValueError("Prompt cannot be empty after stripping whitespace")
            if len(stripped) > 8000:
                raise ValueError("Prompt cannot exceed 8000 characters")
            return stripped

        elif isinstance(v, list):
            # For message arrays, validate each message
            if len(v) == 0:
                raise ValueError("Messages array cannot be empty")

            # Validate total content length across all messages
            total_length = sum(len(msg.content) for msg in v if hasattr(msg, "content"))
            if total_length > 8000:
                raise ValueError("Total prompt content cannot exceed 8000 characters")

            return v

        else:
            raise ValueError("Prompt must be a string or list of Message objects")

    @model_validator(mode="after")
    def normalize_model_fields(self) -> AskRequest:
        """Normalize model_override to model for backward compatibility."""
        # model_override takes precedence over model for backward compatibility
        if self.model_override is not None:
            self.model = self.model_override

        return self

    model_config = ConfigDict(
        title="AskRequest",
        validate_by_name=True,
        validate_by_alias=True,  # Allow both model and model_override field names
        json_schema_extra={
            "examples": [
                {
                    "summary": "Simple text prompt",
                    "description": "Basic text input for simple queries",
                    "value": {
                        "prompt": "What is the capital of France?",
                        "model": "gpt-4o",
                        "stream": False,
                    },
                },
                {
                    "summary": "Chat format with messages",
                    "description": "Structured chat format preserving role information",
                    "value": {
                        "prompt": [
                            {
                                "role": "system",
                                "content": "You are a helpful geography tutor.",
                            },
                            {
                                "role": "user",
                                "content": "What is the capital of France?",
                            },
                            {
                                "role": "assistant",
                                "content": "The capital of France is Paris.",
                            },
                            {"role": "user", "content": "What about Italy?"},
                        ],
                        "model": "llama3",
                        "stream": True,
                    },
                },
                {
                    "summary": "Legacy model_override usage",
                    "description": "Backward compatibility with model_override field",
                    "value": {
                        "prompt": "Translate to French",
                        "model_override": "llama3",  # Legacy field name
                        "stream": False,
                    },
                },
            ]
        },
    )


__all__ = ["Message", "AskRequest"]

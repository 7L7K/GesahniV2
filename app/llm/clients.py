"""LLM client stubs for dry-run mode.

These stubs provide deterministic responses without network calls,
used when DRY_RUN=true or dry_run=True is passed to route_prompt.
"""

import os
from typing import Any


class StubClient:
    """Deterministic stub client that never makes network calls."""

    def __init__(self, *args, **kwargs):
        """Initialize stub client - accepts any args to match real clients."""
        pass

    async def chat_completions_create(self, **kwargs) -> dict[str, Any]:
        """Return deterministic chat completion response."""
        model = kwargs.get("model", "stub-model")
        messages = kwargs.get("messages", [])
        prompt_text = ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                prompt_text = msg.get("content", "")

        # Deterministic response based on prompt hash
        import hashlib

        prompt_hash = hashlib.md5(prompt_text.encode()).hexdigest()[:8]

        return {
            "choices": [
                {"message": {"content": f"Stub response for {model}: {prompt_hash}"}}
            ],
            "usage": {
                "prompt_tokens": len(prompt_text.split()) * 2,
                "completion_tokens": 10,
            },
        }

    async def embeddings_create(self, **kwargs) -> dict[str, Any]:
        """Return deterministic embedding response."""
        text = kwargs.get("input", "")
        if isinstance(text, list):
            text = " ".join(text)

        # Deterministic 1536-dim embedding (matches OpenAI ada-002)
        import hashlib

        text_hash = hashlib.md5(text.encode()).hexdigest()
        # Create deterministic float values from hash
        embedding = []
        for i in range(1536):
            hash_val = int(text_hash[i % len(text_hash)], 16)
            embedding.append((hash_val / 15.0 - 0.5) * 2.0)

        return {
            "data": [{"embedding": embedding}],
            "usage": {"total_tokens": len(text.split()) * 2},
        }

    async def audio_transcriptions_create(self, **kwargs) -> dict[str, Any]:
        """Return deterministic transcription response."""
        return {"text": "Stub transcription: This is a test audio transcription."}


def get_stub_openai_client() -> StubClient:
    """Return stub OpenAI client for dry-run mode."""
    return StubClient()


def get_stub_ollama_client() -> StubClient:
    """Return stub Ollama client for dry-run mode."""
    return StubClient()


# Conditional client factory based on DRY_RUN
def get_openai_client():
    """Get OpenAI client - returns stub in dry-run mode."""
    if os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes"}:
        return get_stub_openai_client()

    # Import real client
    try:
        from openai import AsyncOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAI API key not configured")
        return AsyncOpenAI(api_key=api_key)
    except ImportError:
        raise RuntimeError("OpenAI package not installed")


def get_ollama_client():
    """Get Ollama client - returns stub in dry-run mode."""
    if os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes"}:
        return get_stub_ollama_client()

    # Would normally return real Ollama client
    # For now, just return stub since we don't want network calls
    return get_stub_ollama_client()

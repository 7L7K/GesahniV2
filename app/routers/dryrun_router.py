"""Dry-run backend router for testing and development."""

import asyncio
from typing import Any


async def dryrun_router(payload: dict[str, Any]) -> dict[str, Any]:
    """Dry-run backend with standardized response format.

    Always succeeds and returns mock data for testing.

    Frozen response contract:
    {
      "backend": "dryrun",
      "model": "string",
      "answer": "string",
      "usage": {"input_tokens": 0, "output_tokens": 0}
    }
    """
    # Simulate some processing time
    await asyncio.sleep(0.01)

    model = payload.get("model", "dryrun-model")
    prompt = payload.get("prompt", "")

    # Generate a mock response based on the prompt
    if isinstance(prompt, str):
        answer = (
            f"Dry-run response to: '{prompt[:50]}...'"
            if len(prompt) > 50
            else f"Dry-run response to: '{prompt}'"
        )
    elif isinstance(prompt, list):
        first_msg = prompt[0] if prompt else {}
        content = (
            first_msg.get("content", "")
            if isinstance(first_msg, dict)
            else str(first_msg)
        )
        answer = (
            f"Dry-run response to chat: '{content[:50]}...'"
            if len(content) > 50
            else f"Dry-run response to chat: '{content}'"
        )
    else:
        answer = "Dry-run default response"

    return {
        "backend": "dryrun",
        "model": model,
        "answer": answer,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }

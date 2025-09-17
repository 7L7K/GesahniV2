import os
from typing import Any

_client = None


def _init_client():
    """Lazy initialize OpenAI client.

    Keep import/initialization out of top-level so module import is cheap.
    """
    global _client
    if _client is not None:
        return _client

    # Minimal validation of configuration
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OpenAI API key not configured")

    try:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(api_key=key)
        return _client
    except ImportError:
        raise RuntimeError("OpenAI package not installed. Run: pip install openai")


async def openai_router(payload: dict[str, Any]) -> dict[str, Any]:
    """Call OpenAI backend with standardized response format.

    Frozen response contract:
    {
      "backend": "openai",
      "model": "string",
      "answer": "string",
      "usage": {"input_tokens": 0, "output_tokens": 0}
    }

    Raises RuntimeError if backend unavailable (will be caught as 503).
    """
    # Ensure client exists
    try:
        client = _init_client()
    except Exception as e:
        raise RuntimeError(f"OpenAI backend unavailable: {e}")

    # Extract parameters from payload
    prompt = payload.get("prompt", "")
    model = payload.get("model_override") or payload.get("model") or "gpt-4o"
    gen_opts = payload.get("gen_opts", {})

    # Prepare messages for chat completion
    messages = []
    if isinstance(prompt, list):
        # Handle message array format
        messages = prompt
    else:
        # Handle string prompt format
        messages = [{"role": "user", "content": str(prompt)}]

    try:
        # Make the actual OpenAI API call
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=gen_opts.get("max_tokens", 1000),
            temperature=gen_opts.get("temperature", 0.7),
        )

        # Extract the response
        answer = response.choices[0].message.content
        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        }

        return {
            "backend": "openai",
            "model": model,
            "answer": answer,
            "usage": usage,
        }

    except Exception as e:
        raise RuntimeError(f"OpenAI API call failed: {e}")

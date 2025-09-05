from typing import Dict, Any
import asyncio
import aiohttp
import os
import logging

logger = logging.getLogger(__name__)


async def llama_router(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call LLaMA / Ollama backend with standardized response format.

    Frozen response contract:
    {
      "backend": "llama",
      "model": "string",
      "answer": "string",
      "usage": {"input_tokens": 0, "output_tokens": 0}
    }

    Raises RuntimeError if backend unavailable (will be caught as 503).
    """
    # Minimal config check (expand as needed)
    url = os.getenv("OLLAMA_URL")
    if not url:
        raise RuntimeError("LLaMA/Ollama URL not configured")

    model = payload.get("model", "llama3")
    prompt = payload.get("prompt", "")

    # Prepare Ollama API request
    ollama_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        # Chaos injection for vendor failures
        from app.chaos import chaos_wrap_async, inject_exception
        operation = f"llama_call_{model}"

        async def make_request():
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{url}/api/generate", json=ollama_payload) as response:
                    return response

        response = await chaos_wrap_async("vendor", operation, make_request)
                if response.status != 200:
                    raise RuntimeError(f"Ollama API error: {response.status}")

                result = await response.json()

                return {
                    "backend": "llama",
                    "model": model,
                    "answer": result.get("response", ""),
                    "usage": {
                        "input_tokens": result.get("prompt_eval_count", 0),
                        "output_tokens": result.get("eval_count", 0)
                    }
                }

    except aiohttp.ClientError as e:
        logger.warning(f"Ollama connection error: {e}")
        raise RuntimeError(f"LLaMA backend unavailable: {e}")
    except Exception as e:
        logger.warning(f"Ollama unexpected error: {e}")
        raise RuntimeError(f"LLaMA backend error: {e}")



import os
import httpx
import logging

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

logger = logging.getLogger(__name__)

async def ask_llama(prompt: str, model: str | None = None, timeout: float = 30.0) -> str:
    """Send prompt to Ollama server and return the response text."""
    model = model or OLLAMA_MODEL
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
    except Exception as e:
        logger.exception("Ollama request failed: %s", e)
        raise

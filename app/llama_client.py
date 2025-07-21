import os
from typing import Optional

import requests


def llama_completion(prompt: str, *, model: str = "llama3", temperature: float = 0.7,
                     ollama_url: Optional[str] = None, timeout: int = 30) -> str:
    """Send a completion request to an Ollama server running the given model."""
    ollama_url = ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
    url = f"{ollama_url}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except Exception as e:
        raise RuntimeError(f"Ollama request failed: {e}")

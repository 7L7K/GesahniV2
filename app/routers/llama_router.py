from typing import Dict, Any
import asyncio
import os


async def llama_router(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call LLaMA / Ollama backend.

    Keep this module import-light; perform network/engine calls lazily.
    """
    # Minimal config check (expand as needed)
    url = os.getenv("OLLAMA_URL")
    if not url:
        raise RuntimeError("LLaMA/Ollama URL not configured")

    # TODO: perform real async call to Ollama
    await asyncio.sleep(0)
    return {"backend": "llama", "answer": "(dry-run)"}



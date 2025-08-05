"""Helper to choose between LLaMA and GPT models."""

from __future__ import annotations

from typing import Tuple

from .llama_integration import OLLAMA_MODEL


GPT_DEFAULT_MODEL = "gpt-4o"


def pick_model(prompt: str, intent: str, tokens: int) -> Tuple[str, str]:
    """Return (engine, model_name) for the given prompt.

    ``engine`` is ``"llama"`` or ``"gpt"``; ``model_name`` is the concrete
    model for that engine.  The heuristic mirrors the previous logic in
    :mod:`app.router` and considers prompt length, intent, and token count.
    """

    keywords = {"code", "research", "analyze", "explain"}
    heavy_intents = {"analysis", "research"}
    words = prompt.lower().split()
    if (
        len(words) > 30
        or any(k in words for k in keywords)
        or tokens > 1000
        or intent in heavy_intents
    ):
        return "gpt", GPT_DEFAULT_MODEL
    return "llama", OLLAMA_MODEL or "llama"

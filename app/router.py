import logging
from .llama_client import ask_llama
from .gpt_client import ask_gpt
from .home_assistant import handle_command

logger = logging.getLogger(__name__)

COMPLEX_KEYWORDS = {"code", "research", "analyze", "explain"}


def _should_use_gpt(prompt: str) -> bool:
    words = prompt.lower().split()
    if len(words) > 30:
        return True
    return any(k in words for k in COMPLEX_KEYWORDS)


async def route_prompt(prompt: str) -> str:
    """Decide which backend to use and return the response."""
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        return ha_resp

    if _should_use_gpt(prompt):
        try:
            return await ask_gpt(prompt)
        except Exception:
            logger.exception("GPT failed, falling back to LLaMA")
            return await ask_llama(prompt)
    else:
        try:
            return await ask_llama(prompt)
        except Exception:
            logger.exception("LLaMA failed, falling back to GPT")
            return await ask_gpt(prompt)

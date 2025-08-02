# app/gpt_client.py

import os
import logging
from openai import AsyncOpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

logger = logging.getLogger(__name__)
_client: AsyncOpenAI | None = None

# price in USD per 1k tokens
MODEL_PRICING = {
    "gpt-4o": 0.005,
    "gpt-3.5-turbo": 0.002,
    "gpt-4": 0.01,
}

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client

async def ask_gpt(
    prompt: str, model: str | None = None, system: str | None = None
) -> tuple[str, int, int, float]:
    """Return text, prompt tokens, completion tokens and price per 1k tokens."""
    model = model or OPENAI_MODEL
    client = get_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        text = resp.choices[0].message.content.strip()
        usage = resp.usage or {}
        pt = int(getattr(usage, "prompt_tokens", 0))
        ct = int(getattr(usage, "completion_tokens", 0))
        unit_price = MODEL_PRICING.get(model, 0.0)
        return text, pt, ct, unit_price
    except Exception as e:
        logger.exception("OpenAI request failed: %s", e)
        raise

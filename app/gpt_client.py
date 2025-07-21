import os
import logging
from openai import AsyncOpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

logger = logging.getLogger(__name__)
_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client

async def ask_gpt(prompt: str, model: str | None = None) -> str:
    model = model or OPENAI_MODEL
    client = get_client()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("OpenAI request failed: %s", e)
        raise

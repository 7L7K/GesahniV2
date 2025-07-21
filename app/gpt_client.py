import os
from typing import Optional

import openai


def gpt_completion(prompt: str, *, model: str = "gpt-4o", temperature: float = 0.7,
                   api_key: Optional[str] = None, timeout: int = 30) -> str:
    """Send a completion request to OpenAI's API."""
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = openai.OpenAI(api_key=api_key, timeout=timeout)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"OpenAI request failed: {e}")

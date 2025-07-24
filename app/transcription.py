import os
from openai import AsyncOpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

_client: AsyncOpenAI | None = None

def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client

async def transcribe_file(path: str, model: str | None = None) -> str:
    """Send the audio file to OpenAI whisper API and return the transcript."""
    model = model or TRANSCRIBE_MODEL
    client = _get_client()
    with open(path, "rb") as f:
        resp = await client.audio.transcriptions.create(model=model, file=f)
    return resp.text

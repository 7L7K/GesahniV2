import os
from openai import AsyncClient as OpenAI
from openai import OpenAIError

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

# Initialize once
_client = OpenAI(api_key=OPENAI_API_KEY)


async def transcribe_file(path: str, model: str | None = None) -> str:
    """
    Send the audio file at `path` to OpenAI Whisper via the v1 SDK
    and return the transcript text.
    """
    model = model or TRANSCRIBE_MODEL

    # read file bytes
    try:
        with open(path, "rb") as f:
            resp = await _client.audio.transcriptions.create(
                model=model,
                file=f,
            )
    except OpenAIError as e:
        # catch and re-raise as a simple Exception so your route logs it
        raise RuntimeError(f"Whisper API error: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to read or send {path!r}: {e}") from e

    # the v1 response has `.text`
    return resp.text

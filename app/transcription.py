import os
from openai import AsyncClient as OpenAI
from openai import OpenAIError

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a singleton OpenAI client.

    The original module created the client at import time which raised an
    exception when the ``OPENAI_API_KEY`` environment variable was not set.
    Tests run in an isolated environment without real credentials, so we
    lazily construct the client on first use instead.
    """

    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


async def transcribe_file(path: str, model: str | None = None) -> str:
    """
    Send the audio file at `path` to OpenAI Whisper via the v1 SDK
    and return the transcript text.
    """
    model = model or TRANSCRIBE_MODEL

    # read file bytes
    client = _get_client()
    try:
        with open(path, "rb") as f:
            resp = await client.audio.transcriptions.create(
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

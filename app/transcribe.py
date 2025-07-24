import os
import logging
import openai

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

logger = logging.getLogger(__name__)


def transcribe_file(path: str, model: str | None = None) -> str:
    """Transcribe the given audio file using OpenAI's Whisper API."""
    model = model or WHISPER_MODEL
    try:
        with open(path, "rb") as fh:
            resp = openai.Audio.transcribe(model=model, file=fh, api_key=OPENAI_API_KEY)
        if isinstance(resp, dict):
            text = resp.get("text", "")
        else:
            text = getattr(resp, "text", str(resp))
        return text.strip()
    except Exception as e:
        logger.exception("Transcription failed: %s", e)
        raise

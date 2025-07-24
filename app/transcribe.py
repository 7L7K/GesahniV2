import os
from fastapi import UploadFile
import httpx

TRANSCRIBE_URL = os.getenv("TRANSCRIBE_URL", "http://localhost:8000/transcribe")

async def transcribe_file(file: UploadFile) -> str:
    """Send the audio file to a transcription service and return the text."""
    data = await file.read()
    async with httpx.AsyncClient() as client:
        resp = await client.post(TRANSCRIBE_URL, files={"file": (file.filename, data)})
        resp.raise_for_status()
        result = resp.json()
        return result.get("text", "")

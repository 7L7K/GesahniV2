import os
from fastapi import UploadFile
import httpx
from typing import Any

UPLOAD_URL = os.getenv("UPLOAD_URL", "http://localhost:8000/upload")

async def upload_file(file: UploadFile) -> Any:
    """Upload a file to the configured service and return its response."""
    data = await file.read()
    async with httpx.AsyncClient() as client:
        resp = await client.post(UPLOAD_URL, files={"file": (file.filename, data)})
        resp.raise_for_status()
        return resp.json()

import asyncio
import json
from pathlib import Path
import os, sys
import pytest
os.environ.setdefault("HOME_ASSISTANT_URL", "http://test")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://test")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import history

@pytest.mark.asyncio
async def test_history_appends_entry(tmp_path, monkeypatch):
    file = tmp_path / "hist.json"
    monkeypatch.setattr(history, "HISTORY_FILE", file)
    await history.append_history("123", "hi", "llama", "ok")
    data = json.loads(file.read_text())
    assert data[0]["req_id"] == "123"

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app import status
from app.skills.status_skill import StatusSkill


def test_status(monkeypatch):
    async def fake_request(method, path):
        return {}

    async def fake_llama_status():
        return {"status": "healthy"}

    monkeypatch.setattr(status, "_request", fake_request)
    monkeypatch.setattr(status, "llama_get_status", fake_llama_status)
    skill = StatusSkill()
    m = skill.match("status")
    resp = asyncio.run(skill.run("status", m))
    assert "uptime" in resp

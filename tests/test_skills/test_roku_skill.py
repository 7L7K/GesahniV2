import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.roku_skill import RokuSkill
from app import home_assistant


def test_roku_launch(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert domain == "remote"
        assert data["command"] == "Netflix"

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = RokuSkill()
    m = skill.match("launch Netflix on roku")
    resp = asyncio.run(skill.run("launch Netflix on roku", m))
    assert "Netflix" in resp

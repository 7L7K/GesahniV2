import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.cover_skill import CoverSkill
from app import home_assistant


def test_cover_skill(monkeypatch):
    async def fake_resolve(name):
        return ["cover.blinds"]
    async def fake_call_service(domain, service, data):
        assert service == "open_cover"
    monkeypatch.setattr(home_assistant, "resolve_entity", fake_resolve)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = CoverSkill()
    m = skill.match("open blinds")
    resp = asyncio.run(skill.run("open blinds", m))
    assert "Open" in resp or "open" in resp

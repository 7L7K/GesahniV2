import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.vacuum_skill import VacuumSkill
from app import home_assistant


def test_vacuum_start(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert service == "start"

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = VacuumSkill()
    m = skill.match("start vacuum")
    resp = asyncio.run(skill.run("start vacuum", m))
    assert "started" in resp.lower()

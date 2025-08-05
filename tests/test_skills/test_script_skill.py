import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.script_skill import ScriptSkill
from app import home_assistant


def test_script_skill(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert domain == "script" and service == "turn_on"
        assert data["entity_id"] == "script.house_arrival"

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = ScriptSkill()
    m = skill.match("I'm home")
    resp = asyncio.run(skill.run("I'm home", m))
    assert "house_arrival" in resp

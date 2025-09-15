import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app import home_assistant
from app.skills.climate_skill import ClimateSkill


def test_set_temperature(monkeypatch):
    async def fake_call_service(domain, service, data):
        assert data["temperature"] == 22

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = ClimateSkill()
    m = skill.match("set temperature to 22")
    resp = asyncio.run(skill.run("set temperature to 22", m))
    assert "22" in resp

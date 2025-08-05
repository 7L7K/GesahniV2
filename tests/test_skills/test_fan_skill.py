import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.fan_skill import FanSkill
from app import home_assistant


def test_fan_skill(monkeypatch):
    async def fake_resolve(name):
        return ["fan.purifier"]

    async def fake_call_service(domain, service, data):
        assert domain == "fan" and service == "turn_on"

    monkeypatch.setattr(home_assistant, "resolve_entity", fake_resolve)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = FanSkill()
    m = skill.match("turn on air purifier")
    assert m
    resp = asyncio.run(skill.run("turn on air purifier", m))
    assert "purifier" in resp

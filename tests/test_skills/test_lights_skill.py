import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.lights_skill import LightsSkill
from app import home_assistant


def test_lights_turn_on(monkeypatch):
    async def fake_resolve(name):
        return ["light.kitchen"]

    async def fake_turn_on(entity):
        assert entity == "light.kitchen"

    async def fake_get_states():
        return [
            {
                "entity_id": "light.kitchen",
                "attributes": {"friendly_name": "Kitchen Light"},
            }
        ]

    async def fake_call_service(domain, service, data):
        assert domain == "light" and service == "turn_on"

    monkeypatch.setattr(home_assistant, "resolve_entity", fake_resolve)
    monkeypatch.setattr(home_assistant, "turn_on", fake_turn_on)
    monkeypatch.setattr(home_assistant, "get_states", fake_get_states)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)

    skill = LightsSkill()
    m = skill.match("turn on kitchen lights")
    resp = asyncio.run(skill.run("turn on kitchen lights", m))
    assert "Kitchen" in resp

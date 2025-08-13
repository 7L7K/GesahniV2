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


def test_lights_brightness_bounds(monkeypatch):
    async def fake_get_states():
        return [
            {
                "entity_id": "light.office",
                "attributes": {"friendly_name": "Office"},
            }
        ]

    captured = {}

    async def fake_call_service(domain, service, data):
        captured.update({"service": service, "data": data})

    monkeypatch.setattr(home_assistant, "get_states", fake_get_states)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)

    skill = LightsSkill()
    m = skill.match("set office lights to 150%")
    resp = asyncio.run(skill.run("set office lights to 150%", m))
    assert captured["data"]["brightness_pct"] == 100
    assert "Office" in resp


def test_lights_switch_synonym(monkeypatch):
    async def fake_get_states():
        return [
            {
                "entity_id": "light.desk",
                "attributes": {"friendly_name": "Desk"},
            }
        ]

    captured = {}

    async def fake_call_service(domain, service, data):
        captured.update({"service": service, "data": data})

    monkeypatch.setattr(home_assistant, "get_states", fake_get_states)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)

    skill = LightsSkill()
    m = skill.match("switch off desk light")
    resp = asyncio.run(skill.run("switch off desk light", m))
    assert captured["service"] == "turn_off"
    assert "Desk" in resp


def test_lights_fuzzy_match(monkeypatch):
    async def fake_get_states():
        return [
            {
                "entity_id": "light.living_room_lamp",
                "attributes": {"friendly_name": "Living Room Lamp"},
            }
        ]

    captured = {}

    async def fake_call_service(domain, service, data):
        captured.update({"service": service, "data": data})

    monkeypatch.setattr(home_assistant, "get_states", fake_get_states)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)

    skill = LightsSkill()
    m = skill.match("turn on livingroom lamp")
    resp = asyncio.run(skill.run("turn on livingroom lamp", m))
    assert captured["service"] == "turn_on"
    assert "Livingroom" not in resp  # normalizes casing


def test_lights_not_found(monkeypatch):
    async def fake_get_states():
        return []

    monkeypatch.setattr(home_assistant, "get_states", fake_get_states)

    skill = LightsSkill()
    m = skill.match("turn on unknown lights")
    resp = asyncio.run(skill.run("turn on unknown lights", m))
    assert "Couldn’t find any light" in resp

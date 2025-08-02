import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

import app.home_assistant as ha
from app.skills.device_tracker_skill import DeviceTrackerSkill


async def fake_get_states():
    return [{
        "entity_id": "device_tracker.mom_phone",
        "state": "home",
        "attributes": {"friendly_name": "Mom"},
    }]

def test_device_tracker_skill(monkeypatch):
    monkeypatch.setattr(ha, "get_states", fake_get_states)
    skill = DeviceTrackerSkill()
    m = skill.match("Is Mom home?")
    assert m
    resp = asyncio.run(skill.run("Is Mom home?", m))
    assert "Mom is home" in resp

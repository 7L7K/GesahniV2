import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.door_lock_skill import DoorLockSkill
from app import home_assistant


def test_door_lock(monkeypatch):
    async def fake_resolve(name):
        return ["lock.front"]

    async def fake_call_service(domain, service, data):
        assert domain == "lock" and service == "lock"
        assert data["entity_id"] == "lock.front"

    monkeypatch.setattr(home_assistant, "resolve_entity", fake_resolve)
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = DoorLockSkill()
    m = skill.match("lock front door")
    resp = asyncio.run(skill.run("lock front door", m))
    assert "Lock" in resp

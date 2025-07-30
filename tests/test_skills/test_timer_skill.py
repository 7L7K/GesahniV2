import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.timer_skill import TimerSkill
from app import home_assistant


def test_timer_skill(monkeypatch):
    called = {}
    async def fake_call_service(domain, service, data):
        called.update({"domain": domain, "service": service, "data": data})
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m = skill.match("start a timer for 2 minutes")
    resp = asyncio.run(skill.run("start a timer for 2 minutes", m))
    assert called["domain"] == "timer"
    assert called["service"] == "start"
    assert "2 minutes" in resp


def test_named_timer_cancel_query(monkeypatch):
    events = []
    async def fake_call_service(domain, service, data):
        events.append((service, data["entity_id"]))
    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m = skill.match("start kitchen timer for 1 seconds")
    asyncio.run(skill.run("start kitchen timer for 1 seconds", m))
    m2 = skill.match("how long left on kitchen timer")
    resp = asyncio.run(skill.run("how long left on kitchen timer", m2))
    assert "kitchen" in resp
    m3 = skill.match("cancel kitchen timer")
    asyncio.run(skill.run("cancel kitchen timer", m3))
    assert ("cancel", "timer.kitchen") in events

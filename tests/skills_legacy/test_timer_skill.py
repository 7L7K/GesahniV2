import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app import home_assistant
from app.skills.timer_skill import TimerSkill


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


def test_timer_begin_synonym(monkeypatch):
    called = {}

    async def fake_call_service(domain, service, data):
        called.update({"domain": domain, "service": service, "data": data})

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m = skill.match("begin timer for 3 minutes")
    assert m
    resp = asyncio.run(skill.run("begin timer for 3 minutes", m))
    assert called["domain"] == "timer"
    assert called["service"] == "start"
    assert "3 minutes" in resp


def test_timer_stop_synonym(monkeypatch):
    events = []

    async def fake_call_service(domain, service, data):
        events.append((service, data["entity_id"]))

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    # create a timer, then stop it
    m1 = skill.match("set study timer for 1 minutes")
    asyncio.run(skill.run("set study timer for 1 minutes", m1))
    m2 = skill.match("stop study timer")
    resp = asyncio.run(skill.run("stop study timer", m2))
    assert any(svc == "cancel" for svc, _ in events)
    assert "cancelled" in resp.lower()


def test_timer_mins_synonym(monkeypatch):
    called = {}

    async def fake_call_service(domain, service, data):
        called.update({"domain": domain, "service": service, "data": data})

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m = skill.match("start timer for 2 mins")
    assert m
    asyncio.run(skill.run("start timer for 2 mins", m))
    assert called["service"] == "start"


def test_timer_left_alt_phrase(monkeypatch):
    # Ensure alternate phrasing "left for" matches and returns a string
    events = []

    async def fake_call_service(domain, service, data):
        events.append((service, data["entity_id"]))

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m1 = skill.match("set focus timer for 2 seconds")
    asyncio.run(skill.run("set focus timer for 2 seconds", m1))
    m2 = skill.match("how long left for focus timer")
    resp = asyncio.run(skill.run("how long left for focus timer", m2))
    assert "focus" in resp


def test_timer_default_name(monkeypatch):
    called = {}

    async def fake_call_service(domain, service, data):
        called.update({"entity": data["entity_id"]})

    monkeypatch.setattr(home_assistant, "call_service", fake_call_service)
    skill = TimerSkill()
    m = skill.match("set timer for 1 seconds")
    asyncio.run(skill.run("set timer for 1 seconds", m))
    assert called["entity"].endswith("timer.gesahni")

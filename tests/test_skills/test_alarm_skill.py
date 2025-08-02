import os, sys, asyncio
from types import SimpleNamespace
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.alarm_skill import AlarmSkill
from app.skills import alarm_skill


def test_alarm_skill(monkeypatch):
    info = {}
    def fake_add_job(func, trigger, run_date):
        info["trigger"] = trigger
        info["run_date"] = run_date
    monkeypatch.setattr(alarm_skill, "scheduler", SimpleNamespace(add_job=fake_add_job))
    monkeypatch.setattr(alarm_skill, "start_scheduler", lambda: None)
    skill = AlarmSkill()
    m = skill.match("set an alarm for 6 am")
    resp = asyncio.run(skill.run("set an alarm for 6 am", m))
    assert info["trigger"] == "date"
    assert info["run_date"].hour == 6
    assert "6:00 AM" in resp

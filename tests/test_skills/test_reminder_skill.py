import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

from app.skills.reminder_skill import ReminderSkill, scheduler


def test_reminder_skill(monkeypatch):
    called = {}
    def fake_add_job(func, trigger, seconds):
        called['seconds'] = seconds
    monkeypatch.setattr(scheduler, 'add_job', fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to work out in 2 minutes")
    resp = asyncio.run(skill.run("remind me to work out in 2 minutes", m))
    assert called['seconds'] == 120
    assert "Reminder set" in resp


def test_reminder_recurring(monkeypatch):
    info = {}
    def fake_add_job(func, trigger, **kw):
        info['trigger'] = trigger
        info.update(kw)
    monkeypatch.setattr(scheduler, 'add_job', fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to stretch every day")
    resp = asyncio.run(skill.run("remind me to stretch every day", m))
    assert info['trigger'] == 'interval'
    assert info['days'] == 1
    assert "Recurring" in resp

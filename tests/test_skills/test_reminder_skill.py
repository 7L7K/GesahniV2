import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.skills.reminder_skill import ReminderSkill, scheduler


def test_reminder_skill(monkeypatch):
    called = {}

    def fake_add_job(func, trigger, seconds):
        called["seconds"] = seconds

    monkeypatch.setattr(scheduler, "add_job", fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to work out in 2 minutes")
    resp = asyncio.run(skill.run("remind me to work out in 2 minutes", m))
    assert called["seconds"] == 120
    assert "Reminder set" in resp


def test_reminder_recurring(monkeypatch):
    info = {}

    def fake_add_job(func, trigger, **kw):
        info["trigger"] = trigger
        info.update(kw)

    monkeypatch.setattr(scheduler, "add_job", fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to stretch every day")
    resp = asyncio.run(skill.run("remind me to stretch every day", m))
    assert info["trigger"] == "interval"
    assert info["days"] == 1
    assert "Recurring" in resp


def test_reminder_minutes_variants(monkeypatch):
    info = {}

    def fake_add_job(func, trigger, seconds=None, **kw):
        info["trigger"] = trigger
        if seconds is not None:
            info["seconds"] = seconds

    monkeypatch.setattr(scheduler, "add_job", fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to hydrate in 5 mins")
    resp = asyncio.run(skill.run("remind me to hydrate in 5 mins", m))
    assert info.get("seconds") == 300
    assert "Reminder set" in resp


def test_reminder_hours_variants(monkeypatch):
    info = {}

    def fake_add_job(func, trigger, seconds=None, **kw):
        info["trigger"] = trigger
        if seconds is not None:
            info["seconds"] = seconds

    monkeypatch.setattr(scheduler, "add_job", fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to read in 2 hrs")
    resp = asyncio.run(skill.run("remind me to read in 2 hrs", m))
    assert info.get("seconds") == 7200
    assert "Reminder set" in resp


def test_reminder_tomorrow_at_time(monkeypatch):
    captured = {}

    def fake_add_job(func, trigger, **kw):
        captured["trigger"] = trigger
        captured.update(kw)

    monkeypatch.setattr(scheduler, "add_job", fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me tomorrow at 9am to send report")
    resp = asyncio.run(skill.run("remind me tomorrow at 9am to send report", m))
    assert captured.get("trigger") == "date"
    assert "Reminder set" in resp


def test_reminder_weekday_cron(monkeypatch):
    captured = {}

    def fake_add_job(func, trigger, **kw):
        captured["trigger"] = trigger
        captured.update(kw)

    monkeypatch.setattr(scheduler, "add_job", fake_add_job)
    skill = ReminderSkill()
    m = skill.match("remind me to post every monday")
    resp = asyncio.run(skill.run("remind me to post every monday", m))
    assert captured.get("trigger") == "cron"
    assert captured.get("day_of_week") == "mon"
    assert "Recurring" in resp

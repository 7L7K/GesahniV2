import os, sys, asyncio, json, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

import app.skills.calendar_skill as cal


def test_calendar_skill(tmp_path, monkeypatch):
    today = dt.date.today().isoformat()
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    data = [
        {"date": today, "time": "09:00", "title": "Breakfast"},
        {"date": tomorrow, "time": "10:00", "title": "Meeting"},
    ]
    f = tmp_path / "calendar.json"
    f.write_text(json.dumps(data))
    monkeypatch.setattr(cal, "CAL_FILE", f)

    skill = cal.CalendarSkill()
    m = skill.match("today's events")
    assert m
    resp = asyncio.run(skill.run("today's events", m))
    assert "Breakfast" in resp
    m2 = skill.match("upcoming appointments")
    resp2 = asyncio.run(skill.run("upcoming appointments", m2))
    assert "Meeting" in resp2

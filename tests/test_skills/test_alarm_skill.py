import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

os.environ["ALARMS_STORE"] = tempfile.mkstemp()[1]

from app.skills.alarm_skill import AlarmSkill


def test_alarm_set_list_cancel():
    skill = AlarmSkill()
    m1 = skill.match("set alarm for 7am")
    resp1 = asyncio.run(skill.run("set alarm for 7am", m1))
    assert "07:00 AM" in resp1

    m2 = skill.match("list alarms")
    resp2 = asyncio.run(skill.run("list alarms", m2))
    assert "07:00 AM" in resp2

    m3 = skill.match("cancel alarm for 7am")
    resp3 = asyncio.run(skill.run("cancel alarm for 7am", m3))
    assert "cancelled" in resp3.lower()

    m4 = skill.match("list alarms")
    resp4 = asyncio.run(skill.run("list alarms", m4))
    assert "no alarms" in resp4.lower()

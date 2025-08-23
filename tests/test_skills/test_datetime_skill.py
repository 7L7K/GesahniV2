import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")

from app.skills.datetime_skill import DateTimeSkill


def test_datetime_today():
    s = DateTimeSkill()
    m = s.match("what's today's date")
    out = asyncio.run(s.run("what's today's date", m))
    assert "-" in out


def test_datetime_relative():
    s = DateTimeSkill()
    m = s.match("what is the date tomorrow")
    out = asyncio.run(s.run("what is the date tomorrow", m))
    assert "-" in out

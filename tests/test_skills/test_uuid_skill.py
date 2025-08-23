import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")

from app.skills.uuid_skill import UUIDSkill


def test_uuid_v4_default():
    s = UUIDSkill()
    m = s.match("generate uuid")
    out = asyncio.run(s.run("generate uuid", m))
    assert len(out) >= 36 and out.count("-") >= 4


def test_uuid_v5():
    s = UUIDSkill()
    m = s.match("new uuid v5")
    out = asyncio.run(s.run("new uuid v5", m))
    assert len(out) >= 36 and out.count("-") >= 4



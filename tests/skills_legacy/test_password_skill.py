import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")

from app.skills.password_skill import PasswordSkill


def test_password_default_length():
    s = PasswordSkill()
    m = s.match("generate password")
    out = asyncio.run(s.run("generate password", m))
    assert len(out) == 16


def test_password_custom_length_bounds():
    s = PasswordSkill()
    m = s.match("generate strong password 4")
    out = asyncio.run(s.run("generate strong password 4", m))
    assert len(out) == 8  # clamped min
    m2 = s.match("create password 100")
    out2 = asyncio.run(s.run("create password 100", m2))
    assert len(out2) == 64  # clamped max

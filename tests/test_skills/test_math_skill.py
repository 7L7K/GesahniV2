import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.skills.math_skill import MathSkill


def test_math_basic():
    skill = MathSkill()
    m = skill.match("2 + 3")
    out = asyncio.run(skill.run("2 + 3", m))
    assert out == "5"


def test_percentage():
    skill = MathSkill()
    m = skill.match("25% of 200")
    out = asyncio.run(skill.run("25% of 200", m))
    assert out == "50.0"

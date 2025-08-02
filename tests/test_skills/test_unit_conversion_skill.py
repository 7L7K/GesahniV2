import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL","http://x")
os.environ.setdefault("OLLAMA_MODEL","llama3")
os.environ.setdefault("HOME_ASSISTANT_URL","http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN","token")

from app.skills.unit_conversion_skill import UnitConversionSkill


def test_unit_conversion_skill():
    skill = UnitConversionSkill()
    m = skill.match("how many ounces in 2 liters")
    assert m
    resp = asyncio.run(skill.run("how many ounces in 2 liters", m))
    assert "67.63" in resp
    m2 = skill.match("20 C to F")
    resp2 = asyncio.run(skill.run("20 C to F", m2))
    assert "68.00" in resp2

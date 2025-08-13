import os, sys, asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

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


def test_unit_conversion_litre_alias():
    skill = UnitConversionSkill()
    m = skill.match("how many ounces in 1 litre")
    assert m
    resp = asyncio.run(skill.run("how many ounces in 1 litre", m))
    assert "33.81" in resp


def test_unit_conversion_kilometre_alias():
    skill = UnitConversionSkill()
    m = skill.match("convert 5 kilometres to miles")
    assert m
    resp = asyncio.run(skill.run("convert 5 kilometres to miles", m))
    assert "3.11" in resp


def test_unit_conversion_plural_handling():
    skill = UnitConversionSkill()
    m = skill.match("convert 2 liters to ounces")
    resp = asyncio.run(skill.run("convert 2 liters to ounces", m))
    assert "ounces" in resp


def test_unit_conversion_unsupported():
    skill = UnitConversionSkill()
    m = skill.match("convert 10 apples to oranges")
    resp = asyncio.run(skill.run("convert 10 apples to oranges", m))
    assert resp.lower().startswith("conversion not supported")

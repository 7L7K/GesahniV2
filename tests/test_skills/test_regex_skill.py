import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.skills.regex_skill import RegexExplainSkill


def test_regex_explain_valid():
    s = RegexExplainSkill()
    m = s.match("explain regex: ^foo$")
    out = asyncio.run(s.run("explain regex: ^foo$", m))
    assert "anchors" in out or "valid regex" in out


def test_regex_test_match():
    s = RegexExplainSkill()
    q = "test regex: f(o+)o on foooo"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert "matched:" in out



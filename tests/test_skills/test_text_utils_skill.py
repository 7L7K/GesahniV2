import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.skills.text_utils_skill import TextUtilsSkill


def test_slugify():
    s = TextUtilsSkill()
    q = "slugify: Hello, World! 2025"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert out == "hello-world-2025"


def test_word_count():
    s = TextUtilsSkill()
    q = "word count: one two   three"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert out == "3"



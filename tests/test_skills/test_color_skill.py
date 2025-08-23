import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.skills.color_skill import ColorSkill


def test_color_hex_to_rgb():
    s = ColorSkill()
    q = "rgb of #ff8800"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert out == "rgb(255,136,0)"


def test_color_rgb_to_hex():
    s = ColorSkill()
    q = "hex of (255, 136, 0)"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert out == "#FF8800"



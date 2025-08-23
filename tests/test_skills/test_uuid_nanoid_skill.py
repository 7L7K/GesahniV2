import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.skills.uuid_nanoid_skill import IdSkill


def test_make_id_default():
    s = IdSkill()
    q = "make id"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert 4 <= len(out) <= 64


def test_nanoid_custom_length():
    s = IdSkill()
    q = "nanoid 10"
    m = s.match(q)
    out = asyncio.run(s.run(q, m))
    assert len(out) == 10



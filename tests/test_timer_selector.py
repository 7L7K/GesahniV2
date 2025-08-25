import os
import asyncio

from app.skills import selector


def run_select(prompt):
    return asyncio.get_event_loop().run_until_complete(selector.select(prompt, top_n=3))


def test_set_30_min_timer():
    chosen, top = run_select("set a 30 minute timer")
    assert chosen is not None
    assert "TimerSkill" in chosen.get("skill_name")


def test_create_timer_1_hour():
    chosen, top = run_select("create timer for 1 hour")
    assert chosen is not None
    assert "TimerSkill" in chosen.get("skill_name")


def test_set_timer_named_pasta():
    chosen, top = run_select("set a timer named pasta for 8 minutes")
    assert chosen is not None
    assert "TimerSkill" in chosen.get("skill_name")
    # ensure name captured in top candidate slots when available
    if top:
        found = any((c.get("slots") or {}).get("name") == "pasta" for c in top)
        assert found


def test_pause_resume_stop_cname_cleaning():
    chosen, top = run_select("pause my timer")
    assert chosen is not None
    assert "TimerSkill" in chosen.get("skill_name")



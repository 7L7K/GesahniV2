import asyncio

from app.skills import math_skill as ms


def run_handle(prompt: str):
    return asyncio.get_event_loop().run_until_complete(ms.MathSkill().handle(prompt))


def test_pure_add():
    out = run_handle("9+9")
    assert "18" in out


def test_equals_true():
    out = run_handle("9=9")
    assert "True" in out


def test_equals_false():
    out = run_handle("3*3 = 8")
    assert "False" in out


def test_approx():
    out = run_handle("1/3 ≈ 0.3333333")
    assert "True" in out


def test_power_caret():
    out = run_handle("2^3")
    assert "8" in out


def test_percent_of():
    out = run_handle("20% * 50")
    assert "10" in out


def test_funcs():
    out = run_handle("sqrt(16)")
    assert "4" in out
    out = run_handle("sin(pi/2) = 1")
    assert "True" in out

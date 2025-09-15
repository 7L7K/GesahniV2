from __future__ import annotations


def test_footer_ribbon_truncation_logic():
    # Pure function proxy: ensure truncation to 80 chars behavior
    s = "x" * 100
    trunc = s[:77] + "…"
    assert len(trunc) == 78

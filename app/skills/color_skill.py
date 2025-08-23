from __future__ import annotations

import re

from .base import Skill


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int] | None:
    h = hex_code.lstrip("#").strip()
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return None
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return r, g, b
    except Exception:
        return None


class ColorSkill(Skill):
    PATTERNS = [
        re.compile(r"\brgb of\s*(#[0-9a-fA-F]{3,6})\b", re.I),
        re.compile(
            r"\bhex of\s*\(?(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\)?\b", re.I
        ),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if prompt.lower().startswith("rgb of"):
            rgb = _hex_to_rgb(match.group(1))
            if not rgb:
                return "invalid color"
            return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
        # hex of (r,g,b)
        r, g, b = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return f"#{r:02X}{g:02X}{b:02X}"

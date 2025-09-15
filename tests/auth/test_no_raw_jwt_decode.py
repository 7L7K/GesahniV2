# tests/test_no_raw_jwt_decode.py
import re
from pathlib import Path


def test_no_raw_jwt_decode_outside_helper():
    root = Path(__file__).resolve().parents[1] / "app"
    bad = []
    for p in root.rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        # allow in the central helper module only
        if "security.py" in str(p) and "_jwt_decode" in s:
            continue
        if re.search(r"\bjwt\.decode\(", s):
            bad.append(str(p))
    assert not bad, f"raw jwt.decode found in: {bad}"

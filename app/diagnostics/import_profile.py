from __future__ import annotations

import re
import sys

_LINE = re.compile(r"^import time:\s+(\d+(?:\.\d+)?)\s+\|\s+(\d+(?:\.\d+)?)\s+\|\s+(.+)$")
def parse_stdin() -> list[dict[str, str]]:
    rows = []
    for line in sys.stdin:
        m = _LINE.match(line.strip())
        if m:
            self_ms, cumulative_ms, mod = m.groups()
            rows.append({"self_ms": float(self_ms), "cum_ms": float(cumulative_ms), "module": mod})
    rows.sort(key=lambda r: (-r["self_ms"], r["module"]))
    return rows

if __name__ == "__main__":
    import json
    print(json.dumps(parse_stdin()))

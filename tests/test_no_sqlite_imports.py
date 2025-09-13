import pathlib


def _scan(path: pathlib.Path) -> list[str]:
    hits: list[str] = []
    for p in path.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if ("import sqlite3" in text) or ("import aiosqlite" in text) or ("sqlite://" in text):
            hits.append(str(p))
    return hits


def test_no_sqlite_in_app_modules():
    app_dir = pathlib.Path("app")
    offenders = _scan(app_dir)
    # Allow allowlisting only in debug_*/scripts/ modules per policy
    offenders = [o for o in offenders if "/scripts/" not in o and "/debug_" not in o]
    assert offenders == [], f"SQLite usage found in app/: {offenders}"



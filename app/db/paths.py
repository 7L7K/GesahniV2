from __future__ import annotations

import hashlib
import os
import tempfile
import sys
from pathlib import Path

_DB_CACHE: dict[str, Path] = {}


def resolve_db_path(env_var: str, default_name: str) -> Path:
    """Lazily resolve a DB path for the given environment variable.

    - Prefer explicit env var if set (e.g. CARE_DB, AUTH_DB, MUSIC_DB).
    - If `GESAHNI_TEST_DB_DIR` is set, place files under that directory.
    - If running under pytest, create a per-process temp DB file.
    - Cache the resolved Path for subsequent calls.
    """
    if env_var in _DB_CACHE:
        return _DB_CACHE[env_var]

    # 1) Explicit env var wins
    env_path = os.getenv(env_var)
    if env_path:
        p = Path(env_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        _DB_CACHE[env_var] = p.resolve()
        return _DB_CACHE[env_var]

    # 2) Test dir override (per-worker) e.g. set by pytest hook
    test_dir = os.getenv("GESAHNI_TEST_DB_DIR")
    if test_dir:
        pdir = Path(test_dir)
        try:
            pdir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        p = pdir / f"{env_var.lower()}.db"
        _DB_CACHE[env_var] = p.resolve()
        return _DB_CACHE[env_var]

    # 3) Under pytest: fallback to tempdir with a short digest
    is_pytest = bool(os.getenv("PYTEST_CURRENT_TEST")) or bool(os.getenv("PYTEST_RUNNING")) or ("pytest" in sys.modules)
    if is_pytest:
        ident = os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_RUNNING") or str(os.getpid())
        digest = hashlib.md5(ident.encode()).hexdigest()[:8]
        p = Path(tempfile.gettempdir()) / f".tmp_{env_var.lower()}_{digest}.db"
        _DB_CACHE[env_var] = p.resolve()
        return _DB_CACHE[env_var]

    # 4) Default location in project root
    p = Path(default_name).resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    _DB_CACHE[env_var] = p
    return p
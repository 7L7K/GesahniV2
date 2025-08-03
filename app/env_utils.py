import os
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(".env").resolve()         # absolute path = no cwd surprises
_last_mtime: float | None = None          # None = never loaded

def load_env() -> None:
    """(Re)load .env into os.environ only when the file timestamp bumps."""
    global _last_mtime

    try:
        mtime = _ENV_PATH.stat().st_mtime
    except FileNotFoundError:
        return  # .env doesn’t exist → nothing to load

    if _last_mtime is not None and mtime <= _last_mtime:
        return  # unchanged → skip

    load_dotenv(dotenv_path=_ENV_PATH, override=True)  # explicit path
    _last_mtime = mtime

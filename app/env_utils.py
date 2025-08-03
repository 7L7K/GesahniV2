import os
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path('.env')
_last_mtime = 0.0

def load_env() -> None:
    """Reload .env into os.environ if the file has changed."""
    global _last_mtime
    try:
        mtime = _ENV_PATH.stat().st_mtime
    except FileNotFoundError:
        return
    if mtime <= _last_mtime:
        return
    load_dotenv(override=True)
    _last_mtime = mtime

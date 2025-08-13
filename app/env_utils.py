import os
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(".env").resolve()  # absolute path = no cwd surprises
_ENV_EXAMPLE_PATH = Path(".env.example").resolve()
# Some environments cannot commit dotfiles; support a visible fallback as well
_ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()
_last_mtime: float | None = None  # None = never loaded


def load_env() -> None:
    """(Re)load .env into os.environ only when the file timestamp bumps.

    If ``.env`` is missing but ``.env.example`` exists, load the example as
    a non‑overriding baseline so sensible defaults apply in dev/test.
    """
    global _last_mtime

    try:
        mtime = _ENV_PATH.stat().st_mtime
    except FileNotFoundError:
        # Load example once per process if present
        if _last_mtime is None:
            if _ENV_EXAMPLE_PATH.exists():
                load_dotenv(dotenv_path=_ENV_EXAMPLE_PATH, override=False)
                _last_mtime = 0.0
            elif _ENV_ALT_EXAMPLE_PATH.exists():
                load_dotenv(dotenv_path=_ENV_ALT_EXAMPLE_PATH, override=False)
                _last_mtime = 0.0
        return  # no .env

    if _last_mtime is not None and mtime <= _last_mtime:
        return  # unchanged → skip

    # Do not override existing environment variables so tests and runtime
    # overrides take precedence over .env contents.
    load_dotenv(dotenv_path=_ENV_PATH, override=False)  # explicit path
    _last_mtime = mtime

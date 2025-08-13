import os
import logging
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

_ENV_PATH = Path(".env").resolve()  # absolute path = no cwd surprises
_ENV_EXAMPLE_PATH = Path(".env.example").resolve()
# Some environments cannot commit dotfiles; support a visible fallback as well
_ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()

# Back-compat for older tests that poke this symbol directly
_last_mtime: float | None = None  # None = never loaded

# Newer granular caching across all supported files
_last_mtimes: dict[str, float] | None = None
_loaded_once: bool = False

_logger = logging.getLogger(__name__)


def load_env(force: bool | int | str = False) -> None:
    """Load environment variables with strict precedence and sane reloads.

    Precedence (highest → lowest):
    - .env (if present): overrides existing process env values
    - .env.example and env.example: fill missing keys only (never override)

    Reload rules:
    - Recompute when any tracked file mtime changes
    - Always recompute when force=True
    - In test mode (ENV=test or PYTEST_RUNNING set), bypass caching

    Parsing: handled by python-dotenv; supports quoted values and comments.
    """
    global _last_mtime, _last_mtimes, _loaded_once

    # Normalize force
    _force = str(force).lower() in {"1", "true", "yes", "on"}
    test_mode = os.getenv("ENV", "").strip().lower() == "test" or bool(os.getenv("PYTEST_RUNNING"))

    # Snapshot current mtimes and existence
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return -1.0

    current = {
        "env": _mtime(_ENV_PATH),
        "example": _mtime(_ENV_EXAMPLE_PATH),
        "alt": _mtime(_ENV_ALT_EXAMPLE_PATH),
    }

    # Back-compat: if tests nulled the legacy marker, invalidate new cache too
    if _last_mtime is None:
        _last_mtimes = None

    # Decide whether to skip heavy work
    if not (_force or test_mode):
        if _last_mtimes is not None and _last_mtimes == current:
            # Nothing changed since last run → still ensure example defaults are present
            # Apply examples as non-overriding top-ups so new keys get filled if files changed outside mtime granularity
            filled_example = filled_alt = 0
            if current["example"] >= 0:
                for k, v in (dotenv_values(_ENV_EXAMPLE_PATH) or {}).items():
                    if k and v is not None and k not in os.environ:
                        os.environ[str(k)] = str(v)
                        filled_example += 1
            if current["alt"] >= 0:
                for k, v in (dotenv_values(_ENV_ALT_EXAMPLE_PATH) or {}).items():
                    if k and v is not None and k not in os.environ:
                        os.environ[str(k)] = str(v)
                        filled_alt += 1
            if filled_example or filled_alt:
                _logger.info(
                    "env_loader: .env unchanged; examples filled missing keys (example=%d, alt=%d)",
                    filled_example,
                    filled_alt,
                )
            return

    # Compute counts and apply precedence
    applied_env = filled_example = filled_alt = 0

    # 1) .env overrides existing values
    if current["env"] >= 0:
        for k, v in (dotenv_values(_ENV_PATH) or {}).items():
            if not k or v is None:
                continue
            os.environ[str(k)] = str(v)
            applied_env += 1

    # 2) .env.example fills missing keys only
    if current["example"] >= 0:
        for k, v in (dotenv_values(_ENV_EXAMPLE_PATH) or {}).items():
            if not k or v is None:
                continue
            if k not in os.environ:
                os.environ[str(k)] = str(v)
                filled_example += 1

    # 3) env.example (alt) fills missing keys only
    if current["alt"] >= 0:
        for k, v in (dotenv_values(_ENV_ALT_EXAMPLE_PATH) or {}).items():
            if not k or v is None:
                continue
            if k not in os.environ:
                os.environ[str(k)] = str(v)
                filled_alt += 1

    # Update caches for both legacy and new mechanisms
    _last_mtimes = current
    _last_mtime = current.get("env", -1.0) if current else None
    _loaded_once = True

    # One-liner log with counts and mtimes
    _logger.info(
        "env_loader: applied .env=%d (override), .env.example filled=%d, alt filled=%d | mtimes env=%.6f example=%.6f alt=%.6f force=%s test=%s",
        applied_env,
        filled_example,
        filled_alt,
        current["env"],
        current["example"],
        current["alt"],
        str(_force),
        str(bool(test_mode)),
    )

import logging
import os
from pathlib import Path

from dotenv import dotenv_values

_ENV_PATH = Path(".env").resolve()  # absolute path = no cwd surprises
_ENV_EXAMPLE_PATH = Path(".env.example").resolve()
# Some environments cannot commit dotfiles; support a visible fallback as well
_ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()

# Environment-specific configuration files
_ENV_DEV_PATH = Path("env.dev").resolve()
_ENV_STAGING_PATH = Path("env.staging").resolve()
_ENV_PROD_PATH = Path("env.prod").resolve()
_ENV_LOCALHOST_PATH = Path("env.localhost").resolve()

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
    test_mode = os.getenv("ENV", "").strip().lower() == "test" or bool(
        os.getenv("PYTEST_RUNNING")
    )

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
        "dev": _mtime(_ENV_DEV_PATH),
        "staging": _mtime(_ENV_STAGING_PATH),
        "prod": _mtime(_ENV_PROD_PATH),
        "localhost": _mtime(_ENV_LOCALHOST_PATH),
    }

    # Back-compat: if tests nulled the legacy marker, invalidate new cache too
    if _last_mtime is None:
        _last_mtimes = None

    # Decide whether to skip heavy work
    if not (_force or test_mode):
        if _last_mtimes is not None and _last_mtimes == current:
            # Nothing changed since last run → still ensure example defaults are present
            # Apply examples as non-overriding top-ups so new keys get filled if files changed outside mtime granularity
            filled_example = filled_alt = filled_dev = filled_staging = filled_prod = (
                filled_localhost
            ) = 0
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
            if current["dev"] >= 0:
                for k, v in (dotenv_values(_ENV_DEV_PATH) or {}).items():
                    if k and v is not None and k not in os.environ:
                        os.environ[str(k)] = str(v)
                        filled_dev += 1
            if current["staging"] >= 0:
                for k, v in (dotenv_values(_ENV_STAGING_PATH) or {}).items():
                    if k and v is not None and k not in os.environ:
                        os.environ[str(k)] = str(v)
                        filled_staging += 1
            if current["prod"] >= 0:
                for k, v in (dotenv_values(_ENV_PROD_PATH) or {}).items():
                    if k and v is not None and k not in os.environ:
                        os.environ[str(k)] = str(v)
                        filled_prod += 1
            if current["localhost"] >= 0:
                for k, v in (dotenv_values(_ENV_LOCALHOST_PATH) or {}).items():
                    if k and v is not None and k not in os.environ:
                        os.environ[str(k)] = str(v)
                        filled_localhost += 1
            if (
                filled_example
                or filled_alt
                or filled_dev
                or filled_staging
                or filled_prod
                or filled_localhost
            ):
                _logger.info(
                    "env_loader: .env unchanged; examples filled missing keys (example=%d, alt=%d, dev=%d, staging=%d, prod=%d, localhost=%d)",
                    filled_example,
                    filled_alt,
                    filled_dev,
                    filled_staging,
                    filled_prod,
                    filled_localhost,
                )
            return

    # Compute counts and apply precedence
    applied_env = filled_example = filled_alt = filled_dev = filled_staging = (
        filled_prod
    ) = filled_localhost = 0

    # 1) .env populates missing values only (do not clobber existing env vars)
    #    Tests and monkeypatches expect programmatic env overrides to take
    #    precedence over committed .env files.
    if current["env"] >= 0:
        for k, v in (dotenv_values(_ENV_PATH) or {}).items():
            if not k or v is None:
                continue
            # Respect any existing value (e.g., set by monkeypatch in tests)
            if k in os.environ:
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

    # 4) env.dev fills missing keys only
    if current["dev"] >= 0:
        for k, v in (dotenv_values(_ENV_DEV_PATH) or {}).items():
            if not k or v is None:
                continue
            if k not in os.environ:
                os.environ[str(k)] = str(v)
                filled_dev += 1

    # 5) env.staging fills missing keys only
    if current["staging"] >= 0:
        for k, v in (dotenv_values(_ENV_STAGING_PATH) or {}).items():
            if not k or v is None:
                continue
            if k not in os.environ:
                os.environ[str(k)] = str(v)
                filled_staging += 1

    # 6) env.prod fills missing keys only
    if current["prod"] >= 0:
        for k, v in (dotenv_values(_ENV_PROD_PATH) or {}).items():
            if not k or v is None:
                continue
            if k not in os.environ:
                os.environ[str(k)] = str(v)
                filled_prod += 1

    # 7) env.localhost fills missing keys only
    if current["localhost"] >= 0:
        for k, v in (dotenv_values(_ENV_LOCALHOST_PATH) or {}).items():
            if not k or v is None:
                continue
            if k not in os.environ:
                os.environ[str(k)] = str(v)
                filled_localhost += 1

    # Update caches for both legacy and new mechanisms
    _last_mtimes = current
    _last_mtime = current.get("env", -1.0) if current else None
    _loaded_once = True

    # One-liner log with counts and mtimes
    _logger.info(
        "env_loader: applied .env=%d (override), .env.example filled=%d, alt filled=%d, dev filled=%d, staging filled=%d, prod filled=%d, localhost filled=%d | mtimes env=%.6f example=%.6f alt=%.6f dev=%.6f staging=%.6f prod=%.6f localhost=%.6f force=%s test=%s",
        applied_env,
        filled_example,
        filled_alt,
        filled_dev,
        filled_staging,
        filled_prod,
        filled_localhost,
        current["env"],
        current["example"],
        current["alt"],
        current["dev"],
        current["staging"],
        current["prod"],
        current["localhost"],
        str(_force),
        str(bool(test_mode)),
    )

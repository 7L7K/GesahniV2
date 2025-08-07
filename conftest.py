import os
import sys

# Ensure asynchronous tests have an event loop available and JWT auth works.
os.environ.setdefault("JWT_SECRET", "secret")


def _ensure_openai_error() -> None:
    """Ensure ``openai.OpenAIError`` exists even if tests monkeypatch the module."""
    try:  # pragma: no cover - simple compatibility shim
        sys.modules.pop("openai", None)  # ensure real package reload
        import openai  # type: ignore

        if not hasattr(openai, "OpenAIError"):

            class OpenAIError(Exception):
                pass

            openai.OpenAIError = OpenAIError  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - if OpenAI isn't installed
        pass


# Run once at import time
_ensure_openai_error()


def pytest_collect_file(file_path, path, parent):  # pragma: no cover - hook
    _ensure_openai_error()


pytest_plugins = ("pytest_asyncio",)

import os
import sys
import shutil
import tempfile

# Ensure asynchronous tests have an event loop available and JWT auth works.
os.environ.setdefault("JWT_SECRET", "secret")

# Use an isolated temporary directory for any on-disk Chroma data during tests
_prev_chroma = os.environ.get("CHROMA_PATH")
_tmp_chroma = tempfile.mkdtemp(prefix="chroma_test_")
os.environ["CHROMA_PATH"] = _tmp_chroma


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


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - cleanup hook
    shutil.rmtree(_tmp_chroma, ignore_errors=True)
    if _prev_chroma is not None:
        os.environ["CHROMA_PATH"] = _prev_chroma
    else:
        os.environ.pop("CHROMA_PATH", None)

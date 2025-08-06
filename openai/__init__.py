"""Tiny stub of the ``openai`` package for tests.

Only the ``OpenAIError`` exception and a couple of client classes are required
for the unit tests.  The real network functionality is intentionally omitted.
"""


class OpenAIError(Exception):
    pass


class _Completions:
    async def create(self, *_, **__):  # pragma: no cover - network stub
        raise RuntimeError("openai package not installed")


class _Chat:
    completions = _Completions()


class AsyncOpenAI:  # pragma: no cover - simple placeholder
    def __init__(self, *_, **__):
        pass

    chat = _Chat()

    async def close(self) -> None:  # pragma: no cover - simple stub
        pass


class _Transcriptions:
    async def create(self, *_, **__):  # pragma: no cover - network stub
        raise RuntimeError("openai package not installed")


class _Audio:
    transcriptions = _Transcriptions()


class AsyncClient:  # pragma: no cover - simple placeholder
    def __init__(self, *_, **__):
        pass

    audio = _Audio()

    async def close(self) -> None:  # pragma: no cover - simple stub
        pass


class Audio:  # pragma: no cover - simple placeholder
    @staticmethod
    def transcribe(*_, **__):
        raise RuntimeError("openai package not installed")


__all__ = ["OpenAIError", "AsyncOpenAI", "AsyncClient", "Audio"]

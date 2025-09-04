from typing import Protocol, Dict, Any, Awaitable


class PromptRouter(Protocol):
    """Protocol for prompt router callables.

    A PromptRouter is an async callable that accepts a dict payload and
    returns a dict result. Keeping this as a Protocol avoids coupling to
    concrete implementations and enables typing for DI.
    """

    def __call__(self, payload: Dict[str, Any]) -> Awaitable[Dict[str, Any]]:  # pragma: no cover - typing-only
        ...



from fastapi import Request
from app.domain.prompt_router import PromptRouter


def get_prompt_router(request: Request) -> PromptRouter:
    """Dependency to retrieve the prompt router bound on app.state.

    This defers access to the bound backend until a request-handling
    context is available and avoids globals.
    """
    return request.app.state.prompt_router  # type: ignore[attr-defined]



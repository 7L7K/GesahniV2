import httpx

from .settings import settings


def build_httpx_client(timeout: float | None = None, **kwargs) -> httpx.Client:
    """Create a configured httpx.Client with sane defaults.

    Tests should call this to avoid global shared sessions.
    """
    t = timeout or settings.HTTP_CLIENT_TIMEOUT
    client = httpx.Client(timeout=t, follow_redirects=True, **kwargs)
    return client


def build_async_httpx_client(
    timeout: float | None = None, **kwargs
) -> httpx.AsyncClient:
    t = timeout or settings.HTTP_CLIENT_TIMEOUT
    return httpx.AsyncClient(timeout=t, follow_redirects=True, **kwargs)

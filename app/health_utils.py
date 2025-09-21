import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Literal

from app.env_helpers import env_flag

try:
    import httpx
except Exception:  # pragma: no cover - optional dependency in tests
    httpx = None  # type: ignore


HealthResult = Literal["ok", "error", "skipped"]


async def with_timeout(
    task: Awaitable[HealthResult] | Callable[[], Awaitable[HealthResult]],
    ms: int = 500,
) -> HealthResult:
    """Run a coroutine with a timeout and return "ok" | "error" | "skipped".

    - If the task raises or times out, returns "error".
    - If the task returns any of the expected strings, pass it through.
    - If the task returns truthy/falsey values, map truthy to "ok" and falsy to "error".
    """
    try:
        coro: Awaitable[HealthResult]
        if callable(task):
            coro = task()  # type: ignore[assignment]
        else:
            coro = task  # type: ignore[assignment]
        res = await asyncio.wait_for(coro, timeout=max(0.001, ms / 1000.0))
        if isinstance(res, str) and res in {"ok", "error", "skipped"}:
            return res
        return "ok" if bool(res) else "error"
    except Exception:
        return "error"


async def check_jwt_secret() -> HealthResult:
    # Required readiness: JWT secret configured for auth flows
    jwt_secret = os.getenv("JWT_SECRET")
    jwt_public_key = os.getenv("JWT_PUBLIC_KEY")

    # Check if JWT_SECRET is configured
    if not jwt_secret and not jwt_public_key:
        return "error"

    # Security check: detect insecure default values
    if jwt_secret and jwt_secret.strip().lower() in {
        "change-me",
        "default",
        "placeholder",
        "secret",
        "key",
    }:
        return "error"

    return "ok"


async def check_db() -> HealthResult:
    # Required readiness: ability to open database connection
    try:
        from sqlalchemy import text

        from .db.core import get_async_db

        # Use context manager for proper session management
        async with get_async_db() as session:
            # Simple test query to verify database connectivity
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _http_probe(
    url: str, method: str = "HEAD", timeout_ms: int = 400
) -> HealthResult:
    if httpx is None:
        return "skipped"
    try:
        t = httpx.Timeout(timeout_ms / 1000.0, connect=timeout_ms / 1000.0)
        async with httpx.AsyncClient(timeout=t, follow_redirects=False) as s:
            r = await s.request(method, url)
            # Any response means the service is reachable; 4xx is still fine for liveness
            return "ok" if r is not None else "error"
    except Exception:
        return "error"


async def check_llama() -> HealthResult:
    # Explicit toggle wins
    if (os.getenv("LLAMA_ENABLED") or "").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return "skipped"
    url = (os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL") or "").strip()
    if not url:
        return "skipped"
    # Try a cheap tags/ or root probe; tolerate 4xx
    return await _http_probe(url.rstrip("/") + "/", method="GET")


async def check_home_assistant() -> HealthResult:
    base = (os.getenv("HOME_ASSISTANT_URL") or "").strip()
    if not base:
        return "skipped"
    # HASS commonly requires token; still, a 401 implies reachability
    return await _http_probe(base.rstrip("/") + "/api/")


async def check_qdrant() -> HealthResult:
    base = (os.getenv("QDRANT_URL") or "").strip()
    if not base:
        return "skipped"
    # Qdrant exposes /readyz returning 200 when ready
    return await _http_probe(base.rstrip("/") + "/readyz", method="GET")


async def check_chroma() -> HealthResult:
    # Check if Chroma is configured as the vector store
    vector_store = (os.getenv("VECTOR_STORE") or "").strip().lower()
    if vector_store not in {"chroma", "dual"}:
        return "skipped"

    # For Chroma Cloud, check the API endpoint
    chroma_url = os.getenv("CHROMA_URL")
    if chroma_url:
        return await _http_probe(
            chroma_url.rstrip("/") + "/api/v1/heartbeat", method="GET"
        )

    # For local Chroma, check if the path exists and is accessible
    chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
    if os.path.exists(chroma_path):
        try:
            # Try to initialize Chroma to check if it's working
            import chromadb

            client = chromadb.PersistentClient(path=chroma_path)
            # Simple heartbeat check
            client.list_collections()
            return "ok"
        except Exception:
            return "error"

    return "error"


async def check_spotify() -> HealthResult:
    # Only check when explicitly enabled in env
    if not (
        env_flag(
            "GSNH_ENABLE_SPOTIFY",
            default=False,
            legacy=("PROVIDER_SPOTIFY", "SPOTIFY_ENABLED"),
        )
        and env_flag("GSNH_ENABLE_MUSIC", default=True)
    ):
        return "skipped"
    # HEAD to the public API root; availability-only
    return await _http_probe("https://api.spotify.com", method="HEAD")


__all__ = [
    "with_timeout",
    "check_jwt_secret",
    "check_db",
    "check_llama",
    "check_home_assistant",
    "check_qdrant",
    "check_chroma",
    "check_spotify",
]

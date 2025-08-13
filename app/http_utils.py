import asyncio
import importlib
import logging
from functools import wraps
from typing import Tuple

import httpx
from .otel_utils import start_span

logger = logging.getLogger(__name__)


def _initialize_http_logging() -> None:
    """Configure third-party HTTP libraries to reduce noisy logs.

    At import time we bump ``httpx`` and ``httpcore`` loggers to ``INFO`` if they
    would otherwise emit DEBUG output. This ensures the adjustment happens once
    and avoids touching logger levels during normal request execution.
    """

    if logging.getLogger("httpx").level < logging.INFO:
        logging.getLogger("httpx").setLevel(logging.INFO)
    if logging.getLogger("httpcore").level < logging.INFO:
        logging.getLogger("httpcore").setLevel(logging.INFO)


_initialize_http_logging()


def log_exceptions(module: str):
    """Decorator to log exceptions for async functions."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:  # pragma: no cover - just logging
                logger.warning("%s error: %s", module, e)
                raise

        return wrapper

    return decorator


async def json_request(
    method: str, url: str, **kwargs
) -> Tuple[dict | None, str | None]:
    """Perform an HTTP request and return JSON with retry logic.

    Returns a tuple of ``(data, error)`` where ``error`` is ``None`` on success
    or a short string identifying the failure type.
    """

    delay = 1.0
    for attempt in range(3):
        try:
            httpx_module = httpx
            try:
                llama_module = importlib.import_module("app.llama_integration")
                httpx_module = getattr(llama_module, "httpx", httpx_module)
            except Exception:  # pragma: no cover - fallback if import fails
                pass
            timeout = kwargs.pop("timeout", 10.0)
            factory = getattr(httpx_module, "AsyncClient")
            try:
                cm = factory(timeout=timeout)
            except TypeError:
                cm = factory()
            async with cm as client:
                # Create a client span around outbound call
                with start_span("http.client", {"http.method": method, "http.url": url}):
                    if hasattr(client, "request"):
                        resp = await client.request(method, url, **kwargs)
                    else:  # pragma: no cover - testing hooks
                        func = getattr(client, method.lower())
                        resp = await func(url, **kwargs)
            resp.raise_for_status()
            try:
                return resp.json(), None
            except Exception:
                logger.warning("http.json_decode_failed", extra={"meta": {"url": url}})
                return None, "json_error"
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.warning("http.status_error", extra={"meta": {"status": status, "url": url}})
            if 500 <= status < 600 and attempt < 2:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if status in (401, 403):
                return None, "auth_error"
            if status == 404:
                return None, "not_found"
            return None, "http_error"
        except httpx.RequestError as e:
            logger.warning("http.network_error", extra={"meta": {"url": url, "error": str(e)}})
            if attempt < 2:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            return None, "network_error"
        except Exception as e:  # pragma: no cover - unexpected
            logger.warning("http.unexpected_error", extra={"meta": {"url": url, "error": str(e)}})
            return None, "unknown_error"
    return None, "http_error"

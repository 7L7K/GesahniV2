"""Chaos mode for resilience testing - intentionally break things in development.

This module provides controlled failure injection for testing system resilience.
Only enabled when CHAOS_MODE=1 in development environment.

Usage:
    export CHAOS_MODE=1
    export CHAOS_SEED=42  # Optional: for reproducible chaos
    python -m uvicorn app.main:app --reload

Chaos events are logged and counted for monitoring.
"""

import asyncio
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Chaos configuration
CHAOS_MODE = os.getenv("CHAOS_MODE", "0") == "1"
CHAOS_SEED = int(os.getenv("CHAOS_SEED", "0")) or None

# Chaos probabilities (0.0 to 1.0)
CHAOS_PROBABILITIES = {
    "vendor_latency": float(os.getenv("CHAOS_VENDOR_LATENCY", "0.05")),  # 5% chance
    "vendor_failure": float(os.getenv("CHAOS_VENDOR_FAILURE", "0.02")),  # 2% chance
    "vector_store_failure": float(
        os.getenv("CHAOS_VECTOR_STORE_FAILURE", "0.03")
    ),  # 3% chance
    "vector_store_latency": float(
        os.getenv("CHAOS_VECTOR_STORE_LATENCY", "0.04")
    ),  # 4% chance
    "scheduler_failure": float(
        os.getenv("CHAOS_SCHEDULER_FAILURE", "0.01")
    ),  # 1% chance
    "token_cleanup_failure": float(
        os.getenv("CHAOS_TOKEN_CLEANUP_FAILURE", "0.02")
    ),  # 2% chance
}

# Chaos latency ranges (in seconds)
CHAOS_LATENCY_RANGES = {
    "vendor": (0.5, 3.0),  # 500ms to 3s
    "vector_store": (0.2, 1.5),  # 200ms to 1.5s
}

# Initialize random seed for reproducible chaos
if CHAOS_SEED is not None:
    random.seed(CHAOS_SEED)


def is_chaos_enabled() -> bool:
    """Check if chaos mode is enabled."""
    return CHAOS_MODE


def should_inject_chaos(event_type: str) -> bool:
    """Determine if chaos should be injected for a given event type."""
    if not is_chaos_enabled():
        return False

    probability = CHAOS_PROBABILITIES.get(event_type, 0.0)
    return random.random() < probability


def get_chaos_latency(event_type: str) -> float:
    """Get a random latency duration for chaos injection."""
    latency_range = CHAOS_LATENCY_RANGES.get(event_type, (0.1, 1.0))
    return random.uniform(*latency_range)


async def inject_latency(event_type: str, operation: str) -> None:
    """Inject artificial latency."""
    if not should_inject_chaos(f"{event_type}_latency"):
        return

    latency = get_chaos_latency(event_type)
    logger.warning(
        "💥 CHAOS: Injecting latency",
        extra={
            "meta": {
                "chaos_event": f"{event_type}_latency",
                "operation": operation,
                "latency_seconds": latency,
                "chaos_mode": True,
            }
        },
    )

    # Record chaos latency metric
    try:
        from app.metrics import CHAOS_EVENTS_TOTAL, CHAOS_LATENCY_SECONDS

        CHAOS_LATENCY_SECONDS.labels(
            event_type=event_type, operation=operation
        ).observe(latency)
        CHAOS_EVENTS_TOTAL.labels(
            event_type=f"{event_type}_latency", operation=operation, result="injected"
        ).inc()
    except Exception:
        pass  # Don't fail if metrics aren't available

    await asyncio.sleep(latency)


def inject_exception(
    event_type: str, operation: str, exception_class: type = RuntimeError
) -> None:
    """Inject an artificial exception."""
    if not should_inject_chaos(event_type):
        return

    logger.error(
        "💥 CHAOS: Injecting exception",
        extra={
            "meta": {
                "chaos_event": event_type,
                "operation": operation,
                "exception_class": exception_class.__name__,
                "chaos_mode": True,
            }
        },
    )

    # Record chaos exception metric
    try:
        from app.metrics import CHAOS_EVENTS_TOTAL

        CHAOS_EVENTS_TOTAL.labels(
            event_type=event_type, operation=operation, result="exception"
        ).inc()
    except Exception:
        pass  # Don't fail if metrics aren't available

    raise exception_class(f"Chaos injection: {event_type} failure in {operation}")


async def chaos_wrap_async(
    event_type: str,
    operation: str,
    func: Callable[[], Awaitable[Any]],
    inject_exceptions: bool = True,
) -> Any:
    """Wrap an async function with chaos injection."""
    if not is_chaos_enabled():
        return await func()

    # Inject latency first
    await inject_latency(event_type, operation)

    # Inject exception if enabled
    if inject_exceptions:
        inject_exception(event_type, operation)

    # Execute the function
    return await func()


def chaos_wrap_sync(
    event_type: str,
    operation: str,
    func: Callable[[], Any],
    inject_exceptions: bool = True,
) -> Any:
    """Wrap a sync function with chaos injection."""
    if not is_chaos_enabled():
        return func()

    # Inject latency (sync version)
    if should_inject_chaos(f"{event_type}_latency"):
        latency = get_chaos_latency(event_type)
        logger.warning(
            "💥 CHAOS: Injecting latency",
            extra={
                "meta": {
                    "chaos_event": f"{event_type}_latency",
                    "operation": operation,
                    "latency_seconds": latency,
                    "chaos_mode": True,
                }
            },
        )
        time.sleep(latency)

    # Inject exception if enabled
    if inject_exceptions:
        inject_exception(event_type, operation)

    # Execute the function
    return func()


# Chaos-aware HTTP client wrapper
async def chaos_http_request(
    method: str, url: str, event_type: str = "vendor", **kwargs
) -> Any:
    """Make an HTTP request with chaos injection."""

    async def _make_request():
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, **kwargs) as response:
                return await response.json()

    return await chaos_wrap_async(event_type, f"http_{method}_{url}", _make_request)


# Chaos-aware vector store operations
async def chaos_vector_operation(
    operation: str, func: Callable[[], Awaitable[Any]]
) -> Any:
    """Wrap vector store operations with chaos."""
    return await chaos_wrap_async("vector_store", operation, func)


def chaos_vector_operation_sync(operation: str, func: Callable[[], Any]) -> Any:
    """Wrap sync vector store operations with chaos."""
    return chaos_wrap_sync("vector_store", operation, func)


# Chaos-aware scheduler operations
async def chaos_scheduler_operation(
    operation: str, func: Callable[[], Awaitable[Any]]
) -> Any:
    """Wrap scheduler operations with chaos."""
    return await chaos_wrap_async("scheduler", operation, func, inject_exceptions=True)


# Chaos-aware token cleanup operations
async def chaos_token_cleanup_operation(
    operation: str, func: Callable[[], Awaitable[Any]]
) -> Any:
    """Wrap token cleanup operations with chaos."""
    return await chaos_wrap_async(
        "token_cleanup", operation, func, inject_exceptions=True
    )


def log_chaos_status() -> None:
    """Log current chaos configuration."""
    if not is_chaos_enabled():
        return

    logger.info(
        "🎭 CHAOS MODE ENABLED",
        extra={
            "meta": {
                "chaos_mode": True,
                "chaos_seed": CHAOS_SEED,
                "probabilities": CHAOS_PROBABILITIES,
                "latency_ranges": CHAOS_LATENCY_RANGES,
            }
        },
    )


# Initialize chaos logging
if is_chaos_enabled():
    log_chaos_status()

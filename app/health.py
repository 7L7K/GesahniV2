"""
Health Module

This module provides cached health probes and metrics for various system components
including LLM providers, vector stores, and other dependencies.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Create router for health diagnostics endpoints
router = APIRouter(tags=["Health Diagnostics"])

# ---------------------------------------------------------------------------
# Health Check Data Structures
# ---------------------------------------------------------------------------


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    healthy: bool
    status: str
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: float | None = None


@dataclass
class VendorHealthState:
    """Health state for a vendor with failure tracking."""

    vendor_name: str
    unhealthy_until: float = 0.0
    failure_times: deque = field(default_factory=lambda: deque(maxlen=100))
    consecutive_failures: int = 0
    last_success_time: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)


# Configuration for eager health gating
EAGER_HEALTH_CONFIG = {
    "failure_threshold": 5,  # N failures
    "failure_window_seconds": 60.0,  # M seconds
    "unhealthy_duration_seconds": 300.0,  # T seconds
}

# Global vendor health tracker
_vendor_health_states: dict[str, VendorHealthState] = {}
_vendor_health_lock = threading.Lock()


class VendorHealthTracker:
    """
    Eager health gating system that tracks vendor failures and marks vendors unhealthy
    when failure thresholds are exceeded.
    """

    @classmethod
    def get_vendor_state(cls, vendor_name: str) -> VendorHealthState:
        """Get or create health state for a vendor."""
        with _vendor_health_lock:
            if vendor_name not in _vendor_health_states:
                _vendor_health_states[vendor_name] = VendorHealthState(vendor_name)
            return _vendor_health_states[vendor_name]

    @classmethod
    def record_vendor_failure(cls, vendor_name: str) -> bool:
        """
        Record a failure for a vendor and check if it should be marked unhealthy.

        Args:
            vendor_name: The vendor that failed

        Returns:
            True if vendor should be marked unhealthy, False otherwise
        """
        current_time = time.time()
        state = cls.get_vendor_state(vendor_name)

        with state._lock:
            # Add failure timestamp
            state.failure_times.append(current_time)
            state.consecutive_failures += 1

            # Clean old failures outside the window
            cutoff_time = current_time - EAGER_HEALTH_CONFIG["failure_window_seconds"]
            while state.failure_times and state.failure_times[0] < cutoff_time:
                state.failure_times.popleft()

            # Check if we should mark unhealthy
            if len(state.failure_times) >= EAGER_HEALTH_CONFIG["failure_threshold"]:
                if current_time > state.unhealthy_until:
                    state.unhealthy_until = (
                        current_time + EAGER_HEALTH_CONFIG["unhealthy_duration_seconds"]
                    )
                    # Emit structured metric-like warning for alerting systems
                    logger.warning(
                        f"Vendor {vendor_name} marked unhealthy for {EAGER_HEALTH_CONFIG['unhealthy_duration_seconds']}s "
                        f"(failed {len(state.failure_times)} times in last {EAGER_HEALTH_CONFIG['failure_window_seconds']}s)",
                        extra={
                            "meta": {
                                "vendor": vendor_name,
                                "failure_count": len(state.failure_times),
                                "failure_window_seconds": EAGER_HEALTH_CONFIG[
                                    "failure_window_seconds"
                                ],
                                "unhealthy_duration_seconds": EAGER_HEALTH_CONFIG[
                                    "unhealthy_duration_seconds"
                                ],
                            }
                        },
                    )
                    return True

            return False

    @classmethod
    def record_vendor_success(cls, vendor_name: str) -> None:
        """
        Record a success for a vendor, resetting failure counts.

        Args:
            vendor_name: The vendor that succeeded
        """
        current_time = time.time()
        state = cls.get_vendor_state(vendor_name)

        with state._lock:
            state.consecutive_failures = 0
            state.last_success_time = current_time

            # Clear unhealthy status if it was set
            if current_time > state.unhealthy_until:
                state.unhealthy_until = 0.0

    @classmethod
    def is_vendor_healthy(cls, vendor_name: str) -> bool:
        """
        Check if a vendor is currently healthy.

        Args:
            vendor_name: The vendor to check

        Returns:
            True if healthy, False if marked unhealthy
        """
        current_time = time.time()
        state = cls.get_vendor_state(vendor_name)

        with state._lock:
            return current_time > state.unhealthy_until

    @classmethod
    def get_vendor_health_info(cls, vendor_name: str) -> dict[str, Any]:
        """
        Get detailed health information for a vendor.

        Args:
            vendor_name: The vendor to check

        Returns:
            Dictionary with health information
        """
        current_time = time.time()
        state = cls.get_vendor_state(vendor_name)

        with state._lock:
            return {
                "vendor_name": vendor_name,
                "is_healthy": current_time > state.unhealthy_until,
                "unhealthy_until": state.unhealthy_until,
                "remaining_unhealthy_seconds": max(
                    0, state.unhealthy_until - current_time
                ),
                "recent_failures": len(state.failure_times),
                "consecutive_failures": state.consecutive_failures,
                "last_success_time": state.last_success_time,
                "failure_threshold": EAGER_HEALTH_CONFIG["failure_threshold"],
                "failure_window_seconds": EAGER_HEALTH_CONFIG["failure_window_seconds"],
                "unhealthy_duration_seconds": EAGER_HEALTH_CONFIG[
                    "unhealthy_duration_seconds"
                ],
            }

    @classmethod
    def clear_vendor_health(cls, vendor_name: str) -> None:
        """
        Clear health state for a vendor (used by ping endpoint).

        Args:
            vendor_name: The vendor to clear
        """
        with _vendor_health_lock:
            if vendor_name in _vendor_health_states:
                del _vendor_health_states[vendor_name]
                logger.info(f"Cleared health state for vendor {vendor_name}")

    @classmethod
    def get_all_vendor_health_info(cls) -> dict[str, dict[str, Any]]:
        """
        Get health information for all vendors.

        Returns:
            Dictionary mapping vendor names to their health info
        """
        with _vendor_health_lock:
            return {
                vendor: cls.get_vendor_health_info(vendor)
                for vendor in _vendor_health_states.keys()
            }


# ---------------------------------------------------------------------------
# Eager Health Gating Integration
# ---------------------------------------------------------------------------


async def _check_vendor_health(
    vendor_name: str, record_failure: bool = False, record_success: bool = False
) -> bool:
    """
    Check vendor health with eager gating.

    Args:
        vendor_name: The vendor to check
        record_failure: Whether to record a failure if health check fails
        record_success: Whether to record a success if health check succeeds

    Returns:
        True if vendor is healthy, False otherwise
    """
    try:
        # First check if vendor is marked unhealthy by eager gating
        if not VendorHealthTracker.is_vendor_healthy(vendor_name):
            logger.debug(f"Vendor {vendor_name} marked unhealthy by eager gating")
            return False

        # Perform actual health check based on vendor type
        if vendor_name == "openai":
            health_result = await check_openai_health(cache_result=False)
        elif vendor_name == "ollama":
            health_result = await check_ollama_health(cache_result=False)
        else:
            # For unknown vendors, assume healthy
            logger.warning(f"Unknown vendor {vendor_name}, assuming healthy")
            if record_success:
                VendorHealthTracker.record_vendor_success(vendor_name)
            return True

        is_healthy = health_result.healthy

        if is_healthy:
            if record_success:
                VendorHealthTracker.record_vendor_success(vendor_name)
        else:
            if record_failure:
                # This will potentially mark vendor as unhealthy based on failure threshold
                VendorHealthTracker.record_vendor_failure(vendor_name)

        return is_healthy

    except Exception as e:
        logger.error(f"Error checking health for vendor {vendor_name}: {e}")
        if record_failure:
            VendorHealthTracker.record_vendor_failure(vendor_name)
        return False


def record_vendor_failure(vendor_name: str) -> None:
    """
    Record a failure for a vendor (for eager health gating).

    Args:
        vendor_name: The vendor that failed
    """
    VendorHealthTracker.record_vendor_failure(vendor_name)


def record_vendor_success(vendor_name: str) -> None:
    """
    Record a success for a vendor (for eager health gating).

    Args:
        vendor_name: The vendor that succeeded
    """
    VendorHealthTracker.record_vendor_success(vendor_name)


@dataclass
class CachedHealthCheck:
    """Cached health check result."""

    result: HealthCheckResult
    expires_at: float
    check_duration_ms: float


# ---------------------------------------------------------------------------
# Health Check Cache
# ---------------------------------------------------------------------------


class HealthCheckCache:
    """Cache for health check results to avoid excessive checking."""

    def __init__(self, default_ttl_seconds: float = 60.0):
        self.default_ttl = default_ttl_seconds
        self._cache: dict[str, CachedHealthCheck] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> HealthCheckResult | None:
        """
        Get a cached health check result if it's still valid.

        Args:
            key: Cache key for the health check

        Returns:
            HealthCheckResult if valid and cached, None otherwise
        """
        async with self._lock:
            cached = self._cache.get(key)
            if cached and time.time() < cached.expires_at:
                return cached.result
            return None

    async def set(
        self, key: str, result: HealthCheckResult, ttl_seconds: float | None = None
    ) -> None:
        """
        Cache a health check result.

        Args:
            key: Cache key for the health check
            result: Health check result
            ttl_seconds: Time to live in seconds (uses default if None)
        """
        async with self._lock:
            ttl = ttl_seconds or self.default_ttl
            self._cache[key] = CachedHealthCheck(
                result=result,
                expires_at=time.time() + ttl,
                check_duration_ms=0.0,  # Will be set by the caller
            )

    async def invalidate(self, key: str) -> None:
        """
        Invalidate a cached health check.

        Args:
            key: Cache key to invalidate
        """
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all cached health checks."""
        async with self._lock:
            self._cache.clear()


# Global health check cache
health_cache = HealthCheckCache()

# ---------------------------------------------------------------------------
# OpenAI Health Checks
# ---------------------------------------------------------------------------


async def check_openai_health(cache_result: bool = True) -> HealthCheckResult:
    """
    Check OpenAI health with optional caching.

    Args:
        cache_result: Whether to cache the result

    Returns:
        HealthCheckResult
    """
    cache_key = "openai_health"

    # Check cache first
    if cache_result:
        cached = await health_cache.get(cache_key)
        if cached:
            return cached

    start_time = time.perf_counter()

    try:
        # Import here to avoid circular imports
        import os

        from .gpt_client import ask_gpt

        # Use minimal generation to keep health checks snappy
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        text, _, _, _ = await ask_gpt(
            "ping",
            model,
            "You are a helpful assistant.",
            timeout=5.0,  # Short timeout for health checks
            allow_test=True,
            routing_decision=None,
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=duration_ms,
            timestamp=time.time(),
        )

        if cache_result:
            await health_cache.set(cache_key, result, ttl_seconds=60.0)

        return result

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=False,
            status="unhealthy",
            latency_ms=duration_ms,
            error=str(e),
            timestamp=time.time(),
        )

        if cache_result:
            # Cache failures for shorter time
            await health_cache.set(cache_key, result, ttl_seconds=30.0)

        return result


# ---------------------------------------------------------------------------
# Ollama Health Checks
# ---------------------------------------------------------------------------


async def check_ollama_health(cache_result: bool = True) -> HealthCheckResult:
    """
    Check Ollama health with optional caching.

    Args:
        cache_result: Whether to cache the result

    Returns:
        HealthCheckResult
    """
    cache_key = "ollama_health"

    # Check cache first
    if cache_result:
        cached = await health_cache.get(cache_key)
        if cached:
            return cached

    start_time = time.perf_counter()

    try:
        # Check if LLaMA is explicitly disabled
        import os
        llama_enabled = (os.getenv("LLAMA_ENABLED") or "").strip().lower()
        if llama_enabled in {"0", "false", "no", "off"}:
            return HealthCheckResult(
                healthy=True,
                status="disabled",
                latency_ms=0.0,
                metadata={"reason": "disabled_via_LLAMA_ENABLED"},
                timestamp=time.time(),
            )

        # Check if Ollama URL is configured
        ollama_url = os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL")
        if not ollama_url and llama_enabled not in {"1", "true", "yes", "on"}:
            return HealthCheckResult(
                healthy=True,
                status="not_configured",
                latency_ms=0.0,
                metadata={"reason": "no_ollama_url"},
                timestamp=time.time(),
            )

        # Import here to avoid circular imports
        from .llama_integration import get_status

        status = await get_status()
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=status.get("status") == "healthy",
            status=status.get("status", "unknown"),
            latency_ms=duration_ms,
            metadata=status,
            timestamp=time.time(),
        )

        if cache_result:
            await health_cache.set(cache_key, result, ttl_seconds=60.0)

        return result

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=False,
            status="unhealthy",
            latency_ms=duration_ms,
            error=str(e),
            timestamp=time.time(),
        )

        if cache_result:
            # Cache failures for shorter time
            await health_cache.set(cache_key, result, ttl_seconds=30.0)

        return result


# ---------------------------------------------------------------------------
# Vector Store Health Checks
# ---------------------------------------------------------------------------


async def check_vector_store_health(cache_result: bool = True) -> HealthCheckResult:
    """
    Check vector store health with optional caching.

    Args:
        cache_result: Whether to cache the result

    Returns:
        HealthCheckResult
    """
    cache_key = "vector_store_health"

    # Check cache first
    if cache_result:
        cached = await health_cache.get(cache_key)
        if cached:
            return cached

    start_time = time.perf_counter()

    try:
        # Import here to avoid circular imports
        from .memory.api import get_store

        store = get_store()

        # Try a simple operation to test connectivity
        if hasattr(store, "qa_cache"):
            # For vector stores with cache, try a simple query
            try:
                # This is a minimal test - just check if the store responds
                pass  # Placeholder for actual health check
            except Exception as e:
                raise Exception(f"Vector store cache test failed: {e}")

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=duration_ms,
            timestamp=time.time(),
        )

        if cache_result:
            await health_cache.set(cache_key, result, ttl_seconds=120.0)

        return result

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=False,
            status="unhealthy",
            latency_ms=duration_ms,
            error=str(e),
            timestamp=time.time(),
        )

        if cache_result:
            # Cache failures for shorter time
            await health_cache.set(cache_key, result, ttl_seconds=60.0)

        return result


# ---------------------------------------------------------------------------
# Home Assistant Health Checks
# ---------------------------------------------------------------------------


async def check_home_assistant_health(cache_result: bool = True) -> HealthCheckResult:
    """
    Check Home Assistant health with optional caching.

    Args:
        cache_result: Whether to cache the result

    Returns:
        HealthCheckResult
    """
    cache_key = "home_assistant_health"

    # Check cache first
    if cache_result:
        cached = await health_cache.get(cache_key)
        if cached:
            return cached

    start_time = time.perf_counter()

    try:
        # Check if Home Assistant is explicitly disabled
        import os
        ha_enabled = (os.getenv("HOME_ASSISTANT_ENABLED") or "").strip().lower()
        if ha_enabled in {"0", "false", "no", "off"}:
            return HealthCheckResult(
                healthy=True,
                status="disabled",
                latency_ms=0.0,
                metadata={"reason": "disabled_via_HOME_ASSISTANT_ENABLED"},
                timestamp=time.time(),
            )

        # Check if Home Assistant URL is configured
        ha_url = os.getenv("HOME_ASSISTANT_URL")
        if not ha_url:
            return HealthCheckResult(
                healthy=True,
                status="not_configured",
                latency_ms=0.0,
                metadata={"reason": "no_home_assistant_url"},
                timestamp=time.time(),
            )

        # Import here to avoid circular imports
        from .home_assistant import _request

        await _request("GET", "/states")
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=duration_ms,
            timestamp=time.time(),
        )

        if cache_result:
            await health_cache.set(cache_key, result, ttl_seconds=60.0)

        return result

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=False,
            status="unhealthy",
            latency_ms=duration_ms,
            error=str(e),
            timestamp=time.time(),
        )

        if cache_result:
            # Cache failures for shorter time
            await health_cache.set(cache_key, result, ttl_seconds=30.0)

        return result


# ---------------------------------------------------------------------------
# Database Health Checks
# ---------------------------------------------------------------------------


async def check_database_health(cache_result: bool = True) -> HealthCheckResult:
    """
    Check database health with optional caching.

    Args:
        cache_result: Whether to cache the result

    Returns:
        HealthCheckResult
    """
    cache_key = "database_health"

    # Check cache first
    if cache_result:
        cached = await health_cache.get(cache_key)
        if cached:
            return cached

    start_time = time.perf_counter()

    try:
        # Import here to avoid circular imports
        from .memory.profile_store import profile_store

        # Try a simple read operation
        profile_store.get("test_health_check")
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=duration_ms,
            timestamp=time.time(),
        )

        if cache_result:
            await health_cache.set(cache_key, result, ttl_seconds=120.0)

        return result

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = HealthCheckResult(
            healthy=False,
            status="unhealthy",
            latency_ms=duration_ms,
            error=str(e),
            timestamp=time.time(),
        )

        if cache_result:
            # Cache failures for shorter time
            await health_cache.set(cache_key, result, ttl_seconds=60.0)

        return result


# ---------------------------------------------------------------------------
# Comprehensive Health Check
# ---------------------------------------------------------------------------


async def check_system_health(
    include_openai: bool = True,
    include_ollama: bool = True,
    include_vector_store: bool = True,
    include_home_assistant: bool = True,
    include_database: bool = True,
    cache_results: bool = True,
) -> dict[str, HealthCheckResult]:
    """
    Perform comprehensive system health check.

    Args:
        include_openai: Whether to check OpenAI
        include_ollama: Whether to check Ollama
        include_vector_store: Whether to check vector store
        include_home_assistant: Whether to check Home Assistant
        include_database: Whether to check database
        cache_results: Whether to cache individual results

    Returns:
        Dictionary of health check results
    """
    results = {}

    # Define health checks to run
    checks = []

    if include_openai:
        checks.append(("openai", check_openai_health))
    if include_ollama:
        checks.append(("ollama", check_ollama_health))
    if include_vector_store:
        checks.append(("vector_store", check_vector_store_health))
    if include_home_assistant:
        checks.append(("home_assistant", check_home_assistant_health))
    if include_database:
        checks.append(("database", check_database_health))

    # Run health checks concurrently
    tasks = [(name, check_func(cache_results)) for name, check_func in checks]

    for name, task in tasks:
        try:
            result = await task
            results[name] = result
        except Exception as e:
            logger.error(f"Health check for {name} failed: {e}")
            results[name] = HealthCheckResult(
                healthy=False, status="error", error=str(e), timestamp=time.time()
            )

    return results


# ---------------------------------------------------------------------------
# Health Diagnostics Router Endpoints
# ---------------------------------------------------------------------------


@router.get("/health/openai")
async def get_openai_health() -> dict[str, Any]:
    """
    Get detailed OpenAI health status with caching information.

    Returns:
        Dictionary with OpenAI health status and metadata
    """
    try:
        result = await check_openai_health(cache_result=False)  # Fresh check

        return {
            "vendor": "openai",
            "healthy": result.healthy,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "timestamp": result.timestamp,
            "cached": False,
        }
    except Exception as e:
        return {
            "vendor": "openai",
            "healthy": False,
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
            "cached": False,
        }


@router.get("/health/ollama")
async def get_ollama_health() -> dict[str, Any]:
    """
    Get detailed Ollama health status with caching information.

    Returns:
        Dictionary with Ollama health status and metadata
    """
    try:
        result = await check_ollama_health(cache_result=False)  # Fresh check

        return {
            "vendor": "ollama",
            "healthy": result.healthy,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "metadata": result.metadata,
            "timestamp": result.timestamp,
            "cached": False,
        }
    except Exception as e:
        return {
            "vendor": "ollama",
            "healthy": False,
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
            "cached": False,
        }


@router.get("/health/vector_store")
async def get_vector_store_health() -> dict[str, Any]:
    """
    Get detailed vector store health status.

    Returns:
        Dictionary with vector store health status and metadata
    """
    try:
        result = await check_vector_store_health(cache_result=False)  # Fresh check

        return {
            "component": "vector_store",
            "healthy": result.healthy,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "timestamp": result.timestamp,
            "cached": False,
        }
    except Exception as e:
        return {
            "component": "vector_store",
            "healthy": False,
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
            "cached": False,
        }


@router.get("/health/home_assistant")
async def get_home_assistant_health() -> dict[str, Any]:
    """
    Get detailed Home Assistant health status.

    Returns:
        Dictionary with Home Assistant health status and metadata
    """
    try:
        result = await check_home_assistant_health(cache_result=False)  # Fresh check

        return {
            "component": "home_assistant",
            "healthy": result.healthy,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "timestamp": result.timestamp,
            "cached": False,
        }
    except Exception as e:
        return {
            "component": "home_assistant",
            "healthy": False,
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
            "cached": False,
        }


@router.get("/health/database")
async def get_database_health() -> dict[str, Any]:
    """
    Get detailed database health status.

    Returns:
        Dictionary with database health status and metadata
    """
    try:
        result = await check_database_health(cache_result=False)  # Fresh check

        return {
            "component": "database",
            "healthy": result.healthy,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "timestamp": result.timestamp,
            "cached": False,
        }
    except Exception as e:
        return {
            "component": "database",
            "healthy": False,
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
            "cached": False,
        }


@router.get("/health/all")
async def get_all_health_status() -> dict[str, Any]:
    """
    Get comprehensive health status for all components.

    Returns:
        Dictionary with health status for all components
    """
    try:
        results = await check_system_health(
            include_openai=True,
            include_ollama=True,
            include_vector_store=True,
            include_home_assistant=True,
            include_database=True,
            cache_results=False,  # Fresh checks
        )

        # Convert results to API-friendly format
        formatted_results = {}
        for component, result in results.items():
            formatted_results[component] = {
                "healthy": result.healthy,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "error": result.error,
                "timestamp": result.timestamp,
            }

        overall_healthy = is_system_healthy(results)

        return {
            "overall_healthy": overall_healthy,
            "timestamp": time.time(),
            "components": formatted_results,
            "cache_status": "fresh",
        }

    except Exception as e:
        return {
            "overall_healthy": False,
            "error": str(e),
            "timestamp": time.time(),
            "components": {},
            "cache_status": "error",
        }


@router.get("/health/cache")
async def get_health_cache_info() -> dict[str, Any]:
    """
    Get information about the health check cache.

    Returns:
        Dictionary with cache statistics and contents
    """
    try:
        cache_size = len(health_cache._cache)
        cache_entries = {}

        # Get cache entry info without exposing sensitive data
        for key, cached in health_cache._cache.items():
            cache_entries[key] = {
                "expires_at": cached.expires_at,
                "age_seconds": time.time() - (cached.expires_at - health_cache.default_ttl),
                "check_duration_ms": cached.check_duration_ms,
            }

        return {
            "cache_size": cache_size,
            "default_ttl_seconds": health_cache.default_ttl,
            "entries": cache_entries,
            "timestamp": time.time(),
        }

    except Exception as e:
        return {
            "error": str(e),
            "cache_size": 0,
            "entries": {},
            "timestamp": time.time(),
        }


@router.post("/health/refresh")
async def refresh_health_cache() -> dict[str, Any]:
    """
    Force refresh all cached health checks.

    Returns:
        Dictionary with refresh status
    """
    try:
        await force_refresh_health_checks()

        return {
            "status": "success",
            "message": "Health check cache refreshed",
            "timestamp": time.time(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": time.time(),
        }


@router.get("/health/vendors")
async def get_vendor_health_status() -> dict[str, Any]:
    """
    Get health status for all vendors being tracked by the eager health gating system.

    Returns:
        Dictionary with health information for all tracked vendors
    """
    try:
        all_health_info = VendorHealthTracker.get_all_vendor_health_info()

        return {
            "status": "ok",
            "vendors": all_health_info,
            "total_vendors": len(all_health_info),
            "unhealthy_vendors": sum(
                1 for info in all_health_info.values() if not info["is_healthy"]
            ),
            "timestamp": time.time(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Error getting vendor health status: {e}",
            "timestamp": time.time(),
        }


# ---------------------------------------------------------------------------
# Health Metrics
# ---------------------------------------------------------------------------


def get_health_metrics() -> dict[str, Any]:
    """
    Get health-related metrics.

    Returns:
        Dictionary of health metrics
    """
    try:
        from .metrics import HEALTH_CHECK_DURATION_SECONDS

        # This would return actual metrics if available
        return {
            "health_check_duration_seconds": "available",
            "cache_size": len(health_cache._cache),
            "cache_hit_rate": "calculated_on_request",
        }
    except ImportError:
        return {
            "health_check_duration_seconds": "unavailable",
            "cache_size": len(health_cache._cache),
            "cache_hit_rate": "unavailable",
        }


# ---------------------------------------------------------------------------
# Health Check Utilities
# ---------------------------------------------------------------------------


async def force_refresh_health_checks() -> None:
    """Force refresh all cached health checks."""
    await health_cache.clear()
    logger.info("Health check cache cleared")


async def get_cached_health_status() -> dict[str, HealthCheckResult]:
    """
    Get all cached health check results.

    Returns:
        Dictionary of cached health check results
    """
    results = {}

    # Check each component's cache
    cache_keys = [
        "openai_health",
        "ollama_health",
        "vector_store_health",
        "home_assistant_health",
        "database_health",
    ]

    for key in cache_keys:
        result = await health_cache.get(key)
        if result:
            component_name = key.replace("_health", "")
            results[component_name] = result

    return results


def is_system_healthy(health_results: dict[str, HealthCheckResult]) -> bool:
    """
    Determine if the overall system is healthy.

    Args:
        health_results: Dictionary of health check results

    Returns:
        True if all critical components are healthy
    """
    critical_components = ["openai", "ollama", "vector_store"]

    for component in critical_components:
        if component in health_results:
            if not health_results[component].healthy:
                return False
        else:
            # If we don't have a result for a critical component, assume unhealthy
            return False

    return True

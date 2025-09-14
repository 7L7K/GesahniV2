"""Route collision guard for startup validation.

This module provides comprehensive route collision detection that:
- Fails on duplicate (METHOD, PATH) pairs during startup
- Prints detailed module:function information for every collision
- Supports an allowlist for intentional overlaps (rare)
- Aborts boot on unallowlisted collisions
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# Allowlist for intentional route overlaps (rare exceptions)
# Format: (method, path) -> set of allowed module:function patterns
ROUTE_COLLISION_ALLOWLIST: dict[tuple[str, str], set[str]] = {
    # Add intentional overlaps here as needed
    # Example: ("GET", "/health") -> {"app.api.health:health_endpoint", "app.status:health_check"}
}


def _get_endpoint_info(route) -> str:
    """Extract detailed endpoint information for collision reporting."""
    endpoint = getattr(route, "endpoint", None)
    if not endpoint:
        return "<unknown>"

    try:
        # Get module and qualified name
        module = getattr(endpoint, "__module__", "<unknown>")
        qualname = getattr(endpoint, "__qualname__", "<unknown>")
        getattr(endpoint, "__name__", "<unknown>")

        # Try to get source file information
        source_file = "<unknown>"
        source_line = "<unknown>"
        try:
            import inspect

            source_info = inspect.getsourcelines(endpoint)
            if source_info and len(source_info) > 1:
                source_file = inspect.getfile(endpoint)
                source_line = str(source_info[1])
        except Exception:
            pass

        return f"{module}.{qualname} (file: {source_file}:{source_line})"
    except Exception:
        return repr(endpoint)


def _normalize_path(path: str) -> str:
    """Normalize path for collision detection."""
    if not path:
        return ""

    # Remove trailing slashes for comparison
    path = path.rstrip("/")

    # Ensure leading slash
    if not path.startswith("/"):
        path = "/" + path

    return path


def check_route_collisions(app, fail_on_collision: bool = True) -> None:
    """Check for route collisions and report detailed information.

    Args:
        app: FastAPI application instance
        fail_on_collision: If True, raise exception on unallowlisted collisions

    Raises:
        RuntimeError: If unallowlisted collisions are found and fail_on_collision=True
    """
    logger.info("🔍 Starting route collision analysis...")

    # Track (method, path) -> list of endpoint info
    collision_map: dict[tuple[str, str], list[str]] = defaultdict(list)

    total_routes = 0
    skipped_head_routes = 0

    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)

        if not methods or not path:
            continue

        normalized_path = _normalize_path(path)
        endpoint_info = _get_endpoint_info(route)

        total_routes += 1

        for method in methods:
            # Skip automatic HEAD routes added by Starlette when GET exists
            if method == "HEAD":
                skipped_head_routes += 1
                continue

            key = (method, normalized_path)
            collision_map[key].append(endpoint_info)

    logger.info(
        f"📊 Analyzed {total_routes} routes, skipped {skipped_head_routes} automatic HEAD routes"
    )

    # Find actual collisions (multiple handlers for same method+path)
    collisions_found = 0
    unallowlisted_collisions = []
    allowlisted_collisions = []

    for (method, path), handlers in collision_map.items():
        if len(handlers) <= 1:
            continue

        collisions_found += 1
        allowlist_key = (method, path)

        # Check if this collision is allowlisted
        is_allowlisted = allowlist_key in ROUTE_COLLISION_ALLOWLIST

        if is_allowlisted:
            # Verify all handlers are in the allowlist
            allowed_handlers = ROUTE_COLLISION_ALLOWLIST[allowlist_key]
            actual_handlers = set()

            # Extract module:function patterns from endpoint info
            for handler in handlers:
                # Extract module.function from the detailed info
                if "." in handler:
                    # Split on first space to get module.function part
                    module_func = handler.split()[0]
                    actual_handlers.add(module_func)

            # Check if all actual handlers are allowed
            unallowed_handlers = actual_handlers - allowed_handlers
            if unallowed_handlers:
                # Some handlers are not in allowlist - treat as collision
                collision_info = {
                    "method": method,
                    "path": path,
                    "handlers": handlers,
                    "unallowed_handlers": list(unallowed_handlers),
                    "allowed_handlers": list(allowed_handlers),
                }
                unallowlisted_collisions.append(collision_info)
            else:
                # All handlers are allowlisted - log as info
                collision_info = {
                    "method": method,
                    "path": path,
                    "handlers": handlers,
                    "reason": "Allowlisted intentional overlap",
                }
                allowlisted_collisions.append(collision_info)
        else:
            # Not allowlisted - this is a collision
            collision_info = {
                "method": method,
                "path": path,
                "handlers": handlers,
                "reason": "Unallowlisted collision",
            }
            unallowlisted_collisions.append(collision_info)

    # Report allowlisted collisions (info level)
    if allowlisted_collisions:
        logger.info(
            f"ℹ️ Found {len(allowlisted_collisions)} allowlisted route overlaps:"
        )
        for collision in allowlisted_collisions:
            logger.info(f"  Allowlisted: {collision['method']} {collision['path']}")
            for handler in collision["handlers"]:
                logger.info(f"    → {handler}")
            logger.info("")

    # Report unallowlisted collisions (error level)
    if unallowlisted_collisions:
        logger.error(
            f"🚨 CRITICAL: Found {len(unallowlisted_collisions)} unallowlisted route collisions!"
        )
        logger.error("These collisions will prevent the application from starting.")

        for i, collision in enumerate(unallowlisted_collisions, 1):
            logger.error(
                f"[{i}/{len(unallowlisted_collisions)}] COLLISION: {collision['method']} {collision['path']}"
            )
            logger.error(f"  Reason: {collision['reason']}")

            if "unallowed_handlers" in collision:
                logger.error("  Unallowed handlers:")
                for handler in collision["unallowed_handlers"]:
                    logger.error(f"    ❌ {handler}")
                logger.error("  Allowed handlers:")
                for handler in collision["allowed_handlers"]:
                    logger.error(f"    ✅ {handler}")

            logger.error("  All conflicting handlers:")
            for handler in collision["handlers"]:
                logger.error(f"    → {handler}")
            logger.error("")

        if fail_on_collision:
            error_msg = f"Route collision guard failed: {len(unallowlisted_collisions)} unallowlisted collisions detected"
            logger.error(f"💥 {error_msg}")
            raise RuntimeError(error_msg)
        else:
            logger.warning(
                "⚠️ Route collisions detected but not failing due to fail_on_collision=False"
            )

    # Summary
    if collisions_found == 0:
        logger.info("✅ No route collisions detected - all routes are unique")
    else:
        logger.info(
            f"📈 Collision analysis complete: {collisions_found} total collisions ({len(allowlisted_collisions)} allowlisted, {len(unallowlisted_collisions)} unallowlisted)"
        )


async def init_route_collision_guard():
    """Startup component for route collision detection.

    This should be called during application startup after all routes are registered
    but before the application starts serving requests.
    """
    # Import here to avoid circular imports
    from app.main import app

    try:
        check_route_collisions(app, fail_on_collision=True)
        logger.info("✅ Route collision guard passed")
    except Exception as e:
        logger.error(f"❌ Route collision guard failed: {e}")
        raise


def add_to_allowlist(method: str, path: str, handler_patterns: set[str]) -> None:
    """Add an entry to the route collision allowlist.

    Args:
        method: HTTP method (e.g., "GET", "POST")
        path: Route path (e.g., "/health", "/api/users")
        handler_patterns: Set of allowed module:function patterns
    """
    normalized_path = _normalize_path(path)
    key = (method, normalized_path)
    ROUTE_COLLISION_ALLOWLIST[key] = handler_patterns
    logger.debug(
        f"Added to route collision allowlist: {method} {normalized_path} -> {handler_patterns}"
    )


def remove_from_allowlist(method: str, path: str) -> bool:
    """Remove an entry from the route collision allowlist.

    Args:
        method: HTTP method
        path: Route path

    Returns:
        True if entry was removed, False if it didn't exist
    """
    normalized_path = _normalize_path(path)
    key = (method, normalized_path)
    if key in ROUTE_COLLISION_ALLOWLIST:
        del ROUTE_COLLISION_ALLOWLIST[key]
        logger.debug(
            f"Removed from route collision allowlist: {method} {normalized_path}"
        )
        return True
    return False


def get_allowlist() -> dict[tuple[str, str], set[str]]:
    """Get a copy of the current route collision allowlist."""
    return ROUTE_COLLISION_ALLOWLIST.copy()

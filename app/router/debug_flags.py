"""Debug flags for model routing and dry-run functionality."""

from app import settings


def is_debug_routing_enabled() -> bool:
    """Check if debug model routing is enabled (via settings)."""
    try:
        return settings.debug_model_routing()
    except Exception:
        return False


def is_dry_run_mode() -> bool:
    """Check if dry-run mode is enabled.

    Dry-run mode should only be active when DEBUG_MODEL_ROUTING is explicitly enabled.
    This ensures that dry-run only works for debug-only paths as required.
    """
    return is_debug_routing_enabled()


def should_use_dry_run_response() -> bool:
    """Determine if we should return a dry-run response instead of making actual API calls.

    This is used to limit dry-run to debug-only paths and ensure that
    DEBUG_MODEL_ROUTING returns real calls unless explicitly in dry-run tests.
    """
    return is_debug_routing_enabled() and is_dry_run_mode()


def get_debug_routing_config() -> dict:
    """Get debug routing configuration as a dictionary."""
    return {
        "debug_routing_enabled": is_debug_routing_enabled(),
        "dry_run_mode": is_dry_run_mode(),
        "use_dry_run_response": should_use_dry_run_response(),
    }


def log_debug_routing_info(vendor: str, model: str, reason: str) -> None:
    """Log debug routing information if debug mode is enabled."""
    if is_debug_routing_enabled():
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(
            f"Debug routing: vendor={vendor}, model={model}, reason={reason}, "
            f"dry_run={is_dry_run_mode()}"
        )

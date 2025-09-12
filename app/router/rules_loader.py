"""Router rules loader for YAML-based configuration."""

from typing import Any

import yaml

from app import settings


def get_router_rules() -> dict[str, Any]:
    """Load router rules from YAML file.

    Returns:
        Dict containing router configuration rules
    """
    rules_path = settings.router_rules_path()

    try:
        with open(rules_path) as f:
            rules = yaml.safe_load(f)
            return rules or {}
    except (FileNotFoundError, yaml.YAMLError) as e:
        # Return default values if file not found or invalid
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to load router rules from {rules_path}: {e}")
        return {}


# Cache moved to app/infra/router_rules.py
# Use infra.get_router_rules_cache() instead


def get_cached_router_rules() -> dict[str, Any]:
    """Get cached router rules, loading from file if not cached."""
    from ..infra.router_rules import get_router_rules_cache
    return get_router_rules_cache()

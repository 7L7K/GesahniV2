"""
Comprehensive router configuration tests to ensure all edge cases and behaviors work correctly.
"""

import os

from fastapi import FastAPI

from app.routers.config import build_plan, register_routers


def names(plan):
    return [s.import_path for s in plan]


def test_core_routers_always_present():
    """Test that core routers are always included regardless of environment."""

    # Test in different environments
    for env_var in [None, "dev", "prod", "staging"]:
        if env_var:
            os.environ["ENV"] = env_var

        plan = build_plan()
        plan_names = names(plan)

        # Core routers that should always be present
        core_routers = [
            "app.api.ask:router",
            "app.api.health:router",
            "app.api.root:router",
            "app.status:router",
            "app.api.schema:router",
            "app.api.google_oauth:router",
            "app.api.google:integrations_router",
        ]

        for core_router in core_routers:
            assert (
                core_router in plan_names
            ), f"Core router {core_router} missing in env {env_var}"

        # Clean up
        if env_var:
            del os.environ["ENV"]


def test_preflight_router_conditional():
    """Test that preflight router is included by default but can be disabled."""

    # Test default (preflight enabled)
    plan = build_plan()
    plan_names = names(plan)
    assert any(
        "preflight" in name for name in plan_names
    ), "Preflight router should be included by default"

    # Test preflight disabled
    os.environ["PREFLIGHT_ENABLED"] = "0"
    try:
        plan = build_plan()
        plan_names = names(plan)
        assert not any(
            "preflight" in name for name in plan_names
        ), "Preflight router should be excluded when disabled"
    finally:
        del os.environ["PREFLIGHT_ENABLED"]


def test_router_registration_creates_app():
    """Test that register_routers actually modifies the FastAPI app."""
    app = FastAPI(title="Test App")

    # Count routes before
    initial_routes = len(app.routes)

    # Register routers
    register_routers(app)

    # Count routes after
    final_routes = len(app.routes)

    # Should have added routes
    assert (
        final_routes > initial_routes
    ), "register_routers should add routes to the app"

    # Should have some API routes
    route_paths = [str(route.path) for route in app.routes if hasattr(route, "path")]
    assert any("/v1" in path for path in route_paths), "Should have /v1 API routes"


def test_environment_variable_isolation():
    """Test that environment variables don't leak between tests."""

    # Clear CI-related environment variables to simulate non-CI mode
    ci_vars = ["CI", "PYTEST_CURRENT_TEST"]
    saved_vars = {}

    for var in ci_vars:
        if var in os.environ:
            saved_vars[var] = os.environ[var]
            del os.environ[var]

    try:
        # Get baseline (should have fewer routers)
        plan1 = build_plan()
        baseline_count = len(plan1)

        # Set some env vars to enable integrations
        os.environ["GSNH_ENABLE_SPOTIFY"] = "1"
        os.environ["GSNH_ENABLE_MUSIC"] = "1"
        os.environ["APPLE_OAUTH_ENABLED"] = "1"
        os.environ["DEVICE_AUTH_ENABLED"] = "1"

        plan2 = build_plan()
        expanded_count = len(plan2)

        # Should have more routers when integrations are enabled
        assert (
            expanded_count > baseline_count
        ), f"Should have more routers when integrations enabled (baseline: {baseline_count}, expanded: {expanded_count})"

        # Should include the specific routers
        plan_names = names(plan2)
        assert any(
            "spotify" in name for name in plan_names
        ), "Should include Spotify routers"
        assert any(
            "oauth_apple" in name for name in plan_names
        ), "Should include Apple OAuth routers"
        assert any(
            "auth_device" in name for name in plan_names
        ), "Should include device auth routers"

    finally:
        # Clean up test variables
        for key in [
            "GSNH_ENABLE_SPOTIFY",
            "GSNH_ENABLE_MUSIC",
            "APPLE_OAUTH_ENABLED",
            "DEVICE_AUTH_ENABLED",
        ]:
            if key in os.environ:
                del os.environ[key]

        # Restore original CI variables
        for var, value in saved_vars.items():
            os.environ[var] = value


def test_router_spec_structure():
    """Test that all router specs have required fields."""

    plan = build_plan()

    for spec in plan:
        # Check required attributes exist
        assert hasattr(spec, "import_path"), f"RouterSpec missing import_path: {spec}"
        assert hasattr(spec, "prefix"), f"RouterSpec missing prefix: {spec}"
        assert hasattr(
            spec, "include_in_schema"
        ), f"RouterSpec missing include_in_schema: {spec}"

        # Check import_path format
        assert (
            ":" in spec.import_path
        ), f"Invalid import_path format (should be module:attr): {spec.import_path}"

        # Check prefix is string
        assert isinstance(spec.prefix, str), f"Prefix should be string: {spec.prefix}"


def test_router_plan_consistency():
    """Test that build_plan returns consistent results for same environment."""

    # Set specific environment
    os.environ["ENV"] = "test"
    os.environ["GSNH_ENABLE_SPOTIFY"] = "1"
    os.environ["GSNH_ENABLE_MUSIC"] = "1"

    try:
        plan1 = build_plan()
        plan2 = build_plan()

        # Should be identical
        assert len(plan1) == len(plan2), "Plan lengths should be consistent"

        for spec1, spec2 in zip(plan1, plan2, strict=False):
            assert (
                spec1.import_path == spec2.import_path
            ), f"Inconsistent import_path: {spec1.import_path} != {spec2.import_path}"
            assert (
                spec1.prefix == spec2.prefix
            ), f"Inconsistent prefix: {spec1.prefix} != {spec2.prefix}"

    finally:
        # Clean up
        for key in ["ENV", "GSNH_ENABLE_SPOTIFY", "GSNH_ENABLE_MUSIC"]:
            if key in os.environ:
                del os.environ[key]

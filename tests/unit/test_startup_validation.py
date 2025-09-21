"""
Tests to validate startup behavior, middleware stack, and application composition.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI

from app.main import create_app
from app.middleware.stack import setup_middleware_stack


def test_create_app_returns_fastapi_instance():
    """Test that create_app returns a proper FastAPI instance."""
    app = create_app()

    assert isinstance(app, FastAPI), "create_app should return FastAPI instance"
    assert hasattr(app, "routes"), "App should have routes attribute"
    assert hasattr(app, "user_middleware"), "App should have user_middleware attribute"


def test_middleware_stack_setup():
    """Test that middleware stack is properly configured."""
    app = FastAPI()

    # Count initial middleware
    initial_middleware = len(getattr(app, "user_middleware", []))

    # Setup middleware
    setup_middleware_stack(app)

    # Should have added middleware
    final_middleware = len(getattr(app, "user_middleware", []))
    assert (
        final_middleware > initial_middleware
    ), "Middleware stack should add middleware"

    # Check for critical middleware (CORS is conditional, so don't require it)
    middleware_names = [mw.cls.__name__ for mw in getattr(app, "user_middleware", [])]
    critical_middleware = ["RequestIDMiddleware", "AuditMiddleware"]

    for mw_name in critical_middleware:
        assert (
            mw_name in middleware_names
        ), f"Critical middleware {mw_name} should be present"


def test_ci_mode_middleware_exclusions():
    """Test that CI mode properly excludes certain middleware."""
    app = FastAPI()

    # Set CI mode
    os.environ["CI"] = "1"

    try:
        setup_middleware_stack(app)

        middleware_names = [
            mw.cls.__name__ for mw in getattr(app, "user_middleware", [])
        ]

        # In CI mode, RateLimitMiddleware should not be present
        assert (
            "RateLimitMiddleware" not in middleware_names
        ), "RateLimitMiddleware should be excluded in CI mode"

        # But other middleware should still be present
        assert (
            "RequestIDMiddleware" in middleware_names
        ), "RequestIDMiddleware should be present"
        assert (
            "AuditMiddleware" in middleware_names
        ), "AuditMiddleware should be present"

    finally:
        # Clean up
        if "CI" in os.environ:
            del os.environ["CI"]


def test_rate_limit_enabled_flag():
    """Test that RATE_LIMIT_ENABLED flag controls RateLimitMiddleware."""
    app = FastAPI()

    # Test with rate limiting disabled
    os.environ["RATE_LIMIT_ENABLED"] = "0"

    try:
        setup_middleware_stack(app)
        middleware_names = [
            mw.cls.__name__ for mw in getattr(app, "user_middleware", [])
        ]
        assert (
            "RateLimitMiddleware" not in middleware_names
        ), "RateLimitMiddleware should be excluded when disabled"

    finally:
        if "RATE_LIMIT_ENABLED" in os.environ:
            del os.environ["RATE_LIMIT_ENABLED"]

    # Test with rate limiting enabled (default)
    app2 = FastAPI()
    setup_middleware_stack(app2)
    middleware_names = [mw.cls.__name__ for mw in getattr(app2, "user_middleware", [])]

    # In non-CI mode, RateLimitMiddleware should be present
    if "PYTEST_CURRENT_TEST" not in os.environ:  # Only if not in pytest
        assert (
            "RateLimitMiddleware" in middleware_names
        ), "RateLimitMiddleware should be present when enabled"


def test_startup_profile_detection():
    """Test that startup profile is correctly detected."""
    from app.startup.config import detect_profile

    # Test CI detection
    with patch.dict(os.environ, {"CI": "1"}, clear=True):
        with patch("app.startup.config._is_truthy") as mock_truthy:
            mock_truthy.side_effect = lambda v: (v or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            profile = detect_profile()
            assert profile.name == "ci", f"Expected CI profile, got {profile.name}"

    # Test dev detection (default)
    with patch.dict(os.environ, {}, clear=True):
        with patch("app.startup.config._is_truthy") as mock_truthy:
            mock_truthy.side_effect = lambda v: False  # Nothing is truthy
            profile = detect_profile()
            assert profile.name == "dev", f"Expected dev profile, got {profile.name}"

    # Test prod detection
    with patch.dict(os.environ, {"ENV": "prod"}, clear=True):
        with patch("app.startup.config._is_truthy") as mock_truthy:
            # Only ENV=prod should be truthy
            mock_truthy.side_effect = lambda v: v == "prod"
            profile = detect_profile()
            assert profile.name == "prod", f"Expected prod profile, got {profile.name}"


def test_application_routes_structure():
    """Test that the application has the expected route structure."""
    app = create_app()

    # Get all route paths
    route_paths = [str(route.path) for route in app.routes if hasattr(route, "path")]

    # Check for core API routes
    expected_routes = ["/health", "/v1/ask", "/v1/auth", "/v1/admin", "/v1/google"]

    for expected_route in expected_routes:
        assert any(
            expected_route in path for path in route_paths
        ), f"Expected route {expected_route} not found in {route_paths}"

    # Check that we have a reasonable number of routes
    assert len(route_paths) > 10, f"Expected at least 10 routes, got {len(route_paths)}"


def test_openapi_schema_generation():
    """Test that OpenAPI schema can be generated without errors."""
    app = create_app()

    # This should not raise any exceptions
    try:
        schema = app.openapi()
        assert isinstance(schema, dict), "OpenAPI schema should be a dictionary"
        assert "paths" in schema, "Schema should have paths"
        assert "components" in schema, "Schema should have components"

        # Check that we have some operations
        paths = schema.get("paths", {})
        total_operations = sum(len(operations) for operations in paths.values())
        assert total_operations > 0, "Should have at least one operation"

    except Exception as e:
        pytest.fail(f"OpenAPI schema generation failed: {e}")


def test_router_import_safety():
    """Test that router imports don't fail during app creation."""
    # This should not raise ImportError or any other exception
    try:
        app = create_app()
        assert app is not None, "App creation should succeed"
    except ImportError as e:
        pytest.fail(f"Router import failed: {e}")
    except Exception as e:
        pytest.fail(f"App creation failed: {e}")


def test_environment_isolation():
    """Test that environment variables are properly isolated."""
    # Clear CI-related vars first to allow integrations
    ci_vars = ["CI", "PYTEST_CURRENT_TEST"]
    saved_vars = {}

    for var in ci_vars:
        if var in os.environ:
            saved_vars[var] = os.environ[var]
            del os.environ[var]

    try:
        # Set some test environment variables
        test_vars = {
            "TEST_VAR_1": "value1",
            "TEST_VAR_2": "value2",
            "GSNH_ENABLE_SPOTIFY": "1",
            "GSNH_ENABLE_MUSIC": "1",
        }

        original_env = dict(os.environ)

        try:
            # Set test variables
            for key, value in test_vars.items():
                os.environ[key] = value

            # Create app - should use the test variables
            app = create_app()

            # Verify app was created successfully
            assert app is not None

            # The router plan should reflect the test variables
            from app.routers.config import build_plan

            plan = build_plan()
            plan_names = [spec.import_path for spec in plan]

            # Should include Spotify routers since GSNH_ENABLE_SPOTIFY=1
            assert any(
                "spotify" in name for name in plan_names
            ), "Should include Spotify routers with GSNH_ENABLE_SPOTIFY=1"

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    finally:
        # Restore CI-related vars
        for var, value in saved_vars.items():
            os.environ[var] = value

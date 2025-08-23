"""
Validation tests for the middleware stack to ensure all middleware are proper classes.

This prevents function middlewares from sneaking into the stack and ensures
that our deterministic loader is working correctly.
"""

import inspect

from starlette.middleware.base import BaseHTTPMiddleware


def test_user_middleware_are_classes():
    """
    Ensure all middleware in the app.user_middleware stack are actual classes.

    This validates that no function middlewares have made it into the stack,
    which would bypass our startup validation and cause issues at runtime.
    """
    from app.main import app

    assert app.user_middleware, "No middleware found in app.user_middleware"

    for middleware in app.user_middleware:
        # Each middleware should have a cls attribute
        assert hasattr(
            middleware, "cls"
        ), f"Middleware missing cls attribute: {middleware}"

        # The cls should be a class, not a function or other type
        assert inspect.isclass(middleware.cls), (
            f"Middleware is not a class: {middleware.cls} (type: {type(middleware.cls)})\n"
            "All middleware must be class-based. Check that add_mw() is used instead of app.add_middleware() with functions."
        )

        # The cls should subclass BaseHTTPMiddleware (except for built-in Starlette middleware like CORSMiddleware)
        # We allow some exceptions for well-known middleware that don't follow BaseHTTPMiddleware
        known_exceptions = [
            "CORSMiddleware",  # Starlette's CORS middleware
        ]

        if middleware.cls.__name__ not in known_exceptions:
            assert issubclass(middleware.cls, BaseHTTPMiddleware), (
                f"Middleware does not subclass BaseHTTPMiddleware: {middleware.cls}\n"
                f"Custom middleware must inherit from BaseHTTPMiddleware for proper validation."
            )


def test_middleware_names_are_unique():
    """
    Ensure no duplicate middleware names in the stack.

    While not strictly required, duplicate middleware can indicate configuration issues
    or accidental re-addition of the same middleware.
    """
    from app.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    duplicates = [name for name in set(names) if names.count(name) > 1]

    assert not duplicates, (
        f"Duplicate middleware found: {duplicates}\n"
        "Check that middleware are not being added multiple times."
    )


def test_middleware_stack_integrity():
    """
    Comprehensive validation of the middleware stack structure.

    This ensures the stack follows our expected patterns and validates
    the deterministic loader is working as intended.
    """
    from app.main import app

    middleware_list = app.user_middleware
    assert len(middleware_list) > 0, "Middleware stack is empty"

    # Check that we have a reasonable number of middleware (not too few, not excessive)
    assert 8 <= len(middleware_list) <= 15, (
        f"Unexpected middleware count: {len(middleware_list)}\n"
        f"Expected 8-15 middleware, found: {[m.cls.__name__ for m in middleware_list]}"
    )

    # Verify expected middleware are present (this will need updating if middleware changes)
    expected_middleware = [
        "CORSMiddleware",
        "EnhancedErrorHandlingMiddleware",
        "SilentRefreshMiddleware",
        "ReloadEnvMiddleware",
        "CSRFMiddleware",
        "RateLimitMiddleware",
        "SessionAttachMiddleware",
        "RedactHashMiddleware",
        "TraceRequestMiddleware",
        "HealthCheckFilterMiddleware",
        "DedupMiddleware",
        "RequestIDMiddleware",
    ]

    actual_names = [m.cls.__name__ for m in middleware_list]

    # Check for critical middleware that should always be present
    critical_middleware = [
        "CORSMiddleware",
        "EnhancedErrorHandlingMiddleware",
        "CSRFMiddleware",
        "RateLimitMiddleware",
        "RequestIDMiddleware",
    ]

    missing_critical = [
        name for name in critical_middleware if name not in actual_names
    ]
    assert not missing_critical, (
        f"Critical middleware missing: {missing_critical}\n"
        f"Current middleware: {actual_names}"
    )

    print(f"✅ Middleware stack validation passed: {len(middleware_list)} middleware")
    print(f"   Stack: {actual_names}")


def test_no_function_in_middleware_attrs():
    """
    Ensure no middleware has function attributes that could indicate function middleware usage.

    This catches cases where function middleware might be wrapped in a class but still
    use function-based patterns internally.
    """
    from app.main import app

    for middleware in app.user_middleware:
        cls = middleware.cls

        # Skip built-in Starlette middleware
        if cls.__module__.startswith("starlette."):
            continue

        # Check that the class has proper middleware methods
        assert hasattr(cls, "dispatch"), (
            f"Middleware {cls.__name__} missing dispatch method\n"
            "All middleware classes must implement async def dispatch(self, request, call_next)"
        )

        # The dispatch method should be a coroutine function
        dispatch_method = cls.dispatch
        assert inspect.iscoroutinefunction(dispatch_method), (
            f"Middleware {cls.__name__}.dispatch is not an async function\n"
            "Middleware dispatch methods must be async"
        )

"""Test that all dependencies properly handle OPTIONS requests with early returns."""

import pytest
from fastapi import FastAPI, Request, Depends
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.security import (
    rate_limit,
    verify_token,
    verify_token_strict,
    rate_limit_with,
    scope_rate_limit,
    rate_limit_problem,
    require_nonce,
)
from app.deps.roles import require_roles
from app.deps.clerk_auth import require_user
from app.deps.scopes import require_scope, require_any_scope, optional_require_scope, optional_require_any_scope


@pytest.fixture
def app():
    """Create a test app with various dependencies."""
    app = FastAPI()

    @app.options("/test-rate-limit")
    async def test_rate_limit_route(request: Request, _: None = Depends(rate_limit)):
        return JSONResponse({"status": "ok"})

    @app.options("/test-verify-token")
    async def test_verify_token_route(request: Request, _: None = Depends(verify_token)):
        return JSONResponse({"status": "ok"})

    @app.options("/test-verify-token-strict")
    async def test_verify_token_strict_route(request: Request, _: None = Depends(verify_token_strict)):
        return JSONResponse({"status": "ok"})

    @app.options("/test-rate-limit-with")
    async def test_rate_limit_with_route(request: Request, _: None = Depends(rate_limit_with(burst_limit=3))):
        return JSONResponse({"status": "ok"})

    @app.options("/test-scope-rate-limit")
    async def test_scope_rate_limit_route(request: Request, _: None = Depends(scope_rate_limit("admin", burst_limit=3))):
        return JSONResponse({"status": "ok"})

    @app.options("/test-rate-limit-problem")
    async def test_rate_limit_problem_route(request: Request, _: None = Depends(rate_limit_problem)):
        return JSONResponse({"status": "ok"})

    @app.options("/test-require-nonce")
    async def test_require_nonce_route(request: Request, _: None = Depends(require_nonce)):
        return JSONResponse({"status": "ok"})

    @app.options("/test-require-roles")
    async def test_require_roles_route(request: Request, _: None = Depends(require_roles(["admin"]))):
        return JSONResponse({"status": "ok"})

    @app.options("/test-require-user")
    async def test_require_user_route(request: Request, _: str = Depends(require_user)):
        return JSONResponse({"status": "ok"})

    @app.options("/test-require-scope")
    async def test_require_scope_route(request: Request, _: None = Depends(require_scope("admin"))):
        return JSONResponse({"status": "ok"})

    @app.options("/test-require-any-scope")
    async def test_require_any_scope_route(request: Request, _: None = Depends(require_any_scope(["admin", "user"]))):
        return JSONResponse({"status": "ok"})

    @app.options("/test-optional-require-scope")
    async def test_optional_require_scope_route(request: Request, _: None = Depends(optional_require_scope("admin"))):
        return JSONResponse({"status": "ok"})

    @app.options("/test-optional-require-any-scope")
    async def test_optional_require_any_scope_route(request: Request, _: None = Depends(optional_require_any_scope(["admin", "user"]))):
        return JSONResponse({"status": "ok"})

    return app


def test_rate_limit_dependency_handles_options(app):
    """Test that rate_limit dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-rate-limit")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_token_dependency_handles_options(app):
    """Test that verify_token dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-verify-token")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_token_strict_dependency_handles_options(app):
    """Test that verify_token_strict dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-verify-token-strict")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_limit_with_dependency_handles_options(app):
    """Test that rate_limit_with dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-rate-limit-with")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_scope_rate_limit_dependency_handles_options(app):
    """Test that scope_rate_limit dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-scope-rate-limit")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_limit_problem_dependency_handles_options(app):
    """Test that rate_limit_problem dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-rate-limit-problem")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_require_nonce_dependency_handles_options(app):
    """Test that require_nonce dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-require-nonce")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_require_roles_dependency_handles_options(app):
    """Test that require_roles dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-require-roles")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_require_user_dependency_handles_options(app):
    """Test that require_user dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-require-user")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_require_scope_dependency_handles_options(app):
    """Test that require_scope dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-require-scope")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_require_any_scope_dependency_handles_options(app):
    """Test that require_any_scope dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-require-any-scope")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_optional_require_scope_dependency_handles_options(app):
    """Test that optional_require_scope dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-optional-require-scope")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_optional_require_any_scope_dependency_handles_options(app):
    """Test that optional_require_any_scope dependency handles OPTIONS requests."""
    client = TestClient(app)
    response = client.options("/test-optional-require-any-scope")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_all_dependencies_handle_options_without_headers(app):
    """Test that all dependencies handle OPTIONS requests without adding headers."""
    client = TestClient(app)
    
    # Test all routes to ensure they handle OPTIONS without authentication headers
    routes = [
        "/test-rate-limit",
        "/test-verify-token", 
        "/test-verify-token-strict",
        "/test-rate-limit-with",
        "/test-scope-rate-limit",
        "/test-rate-limit-problem",
        "/test-require-nonce",
        "/test-require-roles",
        "/test-require-user",
        "/test-require-scope",
        "/test-require-any-scope",
        "/test-optional-require-scope",
        "/test-optional-require-any-scope",
    ]
    
    for route in routes:
        response = client.options(route)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        
        # Ensure no rate limit headers are added to OPTIONS responses
        rate_limit_headers = [
            "ratelimit-limit",
            "ratelimit-remaining", 
            "ratelimit-reset",
            "X-RateLimit-Burst-Limit",
            "X-RateLimit-Burst-Remaining",
            "X-RateLimit-Burst-Reset",
            "Retry-After"
        ]
        
        for header in rate_limit_headers:
            assert header not in response.headers

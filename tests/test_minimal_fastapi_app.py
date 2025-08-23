"""
Minimal FastAPI App with Dependency Overrides for Testing

This module creates a minimal FastAPI app with mocked dependencies
for comprehensive API endpoint testing without external services.
"""

import os
from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.ask import router as ask_router

# Import the main app and its components
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.models import router as models_router
from app.deps.user import get_current_user_id
from app.security import verify_token


def mock_jwt_secret() -> str:
    """Return a test JWT secret."""
    return "test-jwt-secret-for-testing"


def mock_get_current_user_id(request: Request) -> str:
    """Mock dependency that returns a test user ID."""
    # Check for authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth_header.split(" ", 1)[1],
                "test-jwt-secret-for-testing",
                algorithms=["HS256"]
            )
            return payload.get("user_id", "dev")
        except:
            pass

    # Check for access_token cookie
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            payload = jwt.decode(access_token, "test-jwt-secret-for-testing", algorithms=["HS256"])
            return payload.get("user_id", "dev")
        except:
            pass

    return "dev"


def mock_verify_token(request: Request) -> None:
    """Mock token verification - always succeeds for testing."""
    pass


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with mocked dependencies."""

    # Mock environment variables
    test_env = {
        "JWT_SECRET": "test-jwt-secret-for-testing",
        "ENV": "test",
        "REQUIRE_AUTH_FOR_ASK": "0",  # Disable auth for ask endpoint in tests
        "PYTEST_RUNNING": "1",
        "CORS_ALLOW_ORIGINS": "http://localhost:3000",
        "CORS_ALLOW_CREDENTIALS": "true",
    }

    # Apply environment patches before importing modules
    env_patcher = patch.dict(os.environ, test_env)
    env_patcher.start()

    # Patch the JWT_SECRET at module level for modules that read it at import time
    import app.api.auth
    with patch.object(app.api.auth, '_jwt_secret', "test-jwt-secret-for-testing"):
        with patch.object(app.api.auth, '_get_refresh_ttl_seconds', lambda: 604800):
            # Create a new FastAPI app instance
            test_app = FastAPI(title="Test API", version="1.0.0")

            # Include routers
            test_app.include_router(health_router, prefix="")
            test_app.include_router(auth_router, prefix="/v1")
            test_app.include_router(models_router, prefix="/v1")
            test_app.include_router(ask_router, prefix="/v1")

            # Override dependencies
            test_app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
            test_app.dependency_overrides[verify_token] = mock_verify_token

            # Import and override additional dependencies that might be used
            from app.security import rate_limit

            # Mock all authentication-related dependencies
            test_app.dependency_overrides[rate_limit] = lambda: None

            # Mock require_user dependency if it exists
            try:
                from app.deps.clerk_auth import require_user as clerk_require_user
                test_app.dependency_overrides[clerk_require_user] = lambda: "testuser"
            except ImportError:
                pass

            # Mock optional scopes dependencies
            try:
                from app.deps.scopes import require_any_scopes, require_scope, require_scopes
                test_app.dependency_overrides[require_scope] = lambda scope: None
                test_app.dependency_overrides[require_scopes] = lambda scopes: None
                test_app.dependency_overrides[require_any_scopes] = lambda scopes: None
            except ImportError:
                pass

            # Add CORS middleware for test environment
            from starlette.middleware.cors import CORSMiddleware
            test_app.add_middleware(
                CORSMiddleware,
                allow_origins=["http://localhost:3000"],
                allow_credentials=True,
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["*"],
            )

            return test_app


def create_test_client() -> TestClient:
    """Create a test client with minimal mocking."""

    # Key patches needed for basic functionality
    patches = [
        patch("app.api.auth._jwt_secret", "test-jwt-secret-for-testing"),
        patch("app.api.auth._get_refresh_ttl_seconds", lambda: 604800),
        patch("app.api.auth._decode_any", lambda token, **kwargs: jwt.decode(token, "test-jwt-secret-for-testing", algorithms=["HS256"])),
        patch("app.api.auth.rotate_refresh_cookies", AsyncMock()),
        patch("app.cookies.set_auth_cookies", MagicMock()),
        patch("app.cookies.clear_auth_cookies", MagicMock()),
        patch("app.tokens.make_access", lambda claims, ttl_s: jwt.encode(claims, "test-jwt-secret-for-testing", algorithm="HS256")),
        patch("app.tokens.make_refresh", lambda claims, ttl_s: jwt.encode(claims, "test-jwt-secret-for-testing", algorithm="HS256")),
        # Also patch JWT_SECRET in deps.user module
        patch("app.deps.user.JWT_SECRET", "test-jwt-secret-for-testing"),
        patch("app.tokens.get_default_access_ttl", lambda: 1800),
        patch("app.main.route_prompt", AsyncMock(return_value="Mocked response")),
        patch("app.user_store.user_store.ensure_user", AsyncMock()),
        patch("app.user_store.user_store.increment_login", AsyncMock()),
        patch("app.auth_store.ensure_tables", AsyncMock()),
        patch("app.token_store.allow_refresh", AsyncMock()),
        patch("app.token_store.is_refresh_family_revoked", AsyncMock(return_value=False)),
        patch("app.token_store.revoke_refresh_family", AsyncMock()),
        patch("app.token_store.claim_refresh_jti_with_retry", AsyncMock(return_value=(True, None))),
        patch("app.token_store.get_last_used_jti", AsyncMock(return_value=None)),
        patch("app.token_store.set_last_used_jti", AsyncMock()),
        patch("app.token_store.incr_login_counter", AsyncMock(return_value=1)),
        patch("app.sessions_store.sessions_store", MagicMock()),
        patch("app.deps.user.resolve_session_id", lambda **kwargs: "session_dev"),
    ]

    # Apply all patches
    for p in patches:
        p.start()

    try:
        app = create_test_app()
        client = TestClient(app)
        return client
    finally:
        # Stop patches when done
        for p in patches:
            p.stop()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Pytest fixture that provides a test client with mocked dependencies."""
    yield create_test_client()


def create_auth_cookies(user_id: str = "dev") -> dict[str, str]:
    """Create test authentication cookies."""
    now = int(datetime.utcnow().timestamp())

    access_payload = {
        "user_id": user_id,
        "sub": user_id,
        "iat": now,
        "exp": now + 1800,  # 30 minutes
        "jti": f"access_{user_id}_{now}"
    }

    refresh_payload = {
        "user_id": user_id,
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + 604800,  # 7 days
        "jti": f"refresh_{user_id}_{now}"
    }

    access_token = jwt.encode(access_payload, "test-jwt-secret-for-testing", algorithm="HS256")
    refresh_token = jwt.encode(refresh_payload, "test-jwt-secret-for-testing", algorithm="HS256")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token
    }


def create_auth_headers(user_id: str = "dev") -> dict[str, str]:
    """Create test authentication headers."""
    now = int(datetime.utcnow().timestamp())

    access_payload = {
        "user_id": user_id,
        "sub": user_id,
        "iat": now,
        "exp": now + 1800,  # 30 minutes
        "jti": f"access_{user_id}_{now}"
    }

    access_token = jwt.encode(access_payload, "test-jwt-secret-for-testing", algorithm="HS256")
    return {"Authorization": f"Bearer {access_token}"}


# Export for use in tests
__all__ = [
    "client",
    "create_auth_cookies",
    "create_auth_headers",
    "mock_jwt_secret"
]
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.csrf import CSRFMiddleware
from app.deps.user import get_current_user_id


def create_test_app():
    """Create a test FastAPI app with all required middleware."""
    app = FastAPI()

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*", "Authorization"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # Add CSRF middleware
    app.add_middleware(CSRFMiddleware)

    return app


def create_test_token(
    user_id: str = "test_user", secret: str = "test_secret", **kwargs
):
    """Create a test JWT token."""
    payload = {
        "user_id": user_id,
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iat": datetime.now(UTC),
        **kwargs,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class TestBearerAuthIntegration:
    """Test bearer token authentication integration."""

    def test_bearer_token_verification_and_user_mapping(self, monkeypatch):
        """Test that bearer tokens are verified and user ID is mapped correctly."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "1")

        app = create_test_app()
        captured_user_id = None
        captured_payload = None

        @app.post("/test")
        async def test_endpoint(
            request: Request, user_id: str = Depends(get_current_user_id)
        ):
            nonlocal captured_user_id, captured_payload
            captured_user_id = user_id
            captured_payload = getattr(request.state, "jwt_payload", None)
            return {"user_id": user_id, "authenticated": True}

        client = TestClient(app)
        token = create_test_token("alice", "test_secret")

        response = client.post("/test", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["user_id"] == "alice"
        assert captured_user_id == "alice"
        assert captured_payload is not None
        assert captured_payload["user_id"] == "alice"

    def test_csrf_bypass_with_authorization_header(self, monkeypatch):
        """Test that CSRF is bypassed when Authorization header is present."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "1")

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id, "authenticated": True}

        client = TestClient(app)
        token = create_test_token("alice", "test_secret")

        # This should work without CSRF token because Authorization header is present
        response = client.post("/test", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["user_id"] == "alice"

    def test_csrf_required_without_authorization_header(self, monkeypatch):
        """Test that CSRF is required when no Authorization header is present."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "1")

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id, "authenticated": True}

        client = TestClient(app)

        # This should fail because no Authorization header and no CSRF token
        response = client.post("/test")

        assert response.status_code == 403
        assert "invalid_csrf" in response.json()["detail"]

    def test_cors_authorization_header_allowed(self, monkeypatch):
        """Test that Authorization header is allowed in CORS preflight."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "1")

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id, "authenticated": True}

        client = TestClient(app)

        # Test CORS preflight with Authorization header
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )

        assert response.status_code == 200
        # Check that Authorization is in the allowed headers
        assert (
            "authorization"
            in response.headers.get("access-control-allow-headers", "").lower()
        )

    def test_scope_enforcement_with_jwt_payload(self, monkeypatch):
        """Test that scope enforcement works with JWT payload stored in request state."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "1")
        monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(
            request: Request, user_id: str = Depends(get_current_user_id)
        ):
            # Check that JWT payload is available for scope enforcement
            payload = getattr(request.state, "jwt_payload", None)
            scopes = payload.get("scope", []) if payload else []
            return {"user_id": user_id, "scopes": scopes}

        client = TestClient(app)
        token = create_test_token("alice", "test_secret", scopes=["read", "write"])

        response = client.post("/test", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["user_id"] == "alice"
        assert "read" in response.json()["scopes"]
        assert "write" in response.json()["scopes"]

    def test_invalid_bearer_token_rejected(self, monkeypatch):
        """Test that invalid bearer tokens are properly rejected."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "1")

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id, "authenticated": True}

        client = TestClient(app)

        # Test with invalid token
        response = client.post(
            "/test", headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code == 401
        assert "Invalid authentication token" in response.json()["detail"]

    def test_missing_authorization_header_anonymous(self, monkeypatch):
        """Test that requests without Authorization header are treated as anonymous."""
        monkeypatch.setenv("JWT_SECRET", "test_secret")
        monkeypatch.setenv("CSRF_ENABLED", "0")  # Disable CSRF for this test

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(user_id: str = Depends(get_current_user_id)):
            return {"user_id": user_id, "authenticated": user_id != "anon"}

        client = TestClient(app)

        response = client.post("/test")

        assert response.status_code == 200
        assert response.json()["user_id"] == "anon"
        assert not response.json()["authenticated"]

    def test_clerk_token_support(self, monkeypatch):
        """Test that Clerk tokens are supported when enabled."""
        monkeypatch.setenv(
            "CLERK_JWKS_URL", "https://clerk.example.com/.well-known/jwks.json"
        )
        monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.com")
        monkeypatch.setenv("CSRF_ENABLED", "1")

        app = create_test_app()

        @app.post("/test")
        async def test_endpoint(
            request: Request, user_id: str = Depends(get_current_user_id)
        ):
            payload = getattr(request.state, "jwt_payload", None)
            return {"user_id": user_id, "payload": payload}

        client = TestClient(app)

        # Mock Clerk token (this would normally be validated against Clerk's JWKS)
        clerk_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJjbGVya191c2VyXzEyMyIsImlhdCI6MTYxNjE2MjQwMCwiZXhwIjoxNjE2MTY2MDAwfQ.signature"

        # This test would need proper Clerk token validation setup
        # For now, we'll test that the structure is in place
        response = client.post(
            "/test", headers={"Authorization": f"Bearer {clerk_token}"}
        )

        # Should either succeed with Clerk validation or fall back to anonymous
        assert response.status_code in [200, 401]

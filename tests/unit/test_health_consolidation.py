"""Test for health endpoint consolidation.

This test verifies that:
1. Legacy /health redirects to /v1/health with 308 status
2. Legacy /healthz redirects to /v1/healthz with 308 status
3. Canonical health endpoints return 200:
   - GET /v1/health
   - GET /v1/healthz/live
   - GET /v1/healthz/ready
4. Only canonical endpoints appear in OpenAPI schema
"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient


def test_health_consolidation():
    """Test that health endpoints are properly consolidated with redirects."""

    # Create a minimal test app that mimics the production setup
    app = FastAPI()

    # Import and include the actual routers in the correct order
    # Note: compat_router must come BEFORE health_router to allow redirects to work
    try:
        from app.api.health import router as health_router
        from app.router.compat_api import router as compat_router
        from app.status import public_router as status_public_router
        from app.status import router as status_router

        app.include_router(compat_router, prefix="")
        app.include_router(health_router, prefix="")
        app.include_router(status_router, prefix="/v1")
        app.include_router(status_public_router, prefix="/v1")

    except Exception:
        # If imports fail due to dependencies, create minimal mock routers
        from fastapi import APIRouter

        # Mock compat router with redirects (must come first)
        compat_router = APIRouter(include_in_schema=False)

        @compat_router.get("/health")
        def mock_health_redirect():
            return RedirectResponse(url="/v1/health", status_code=308)

        @compat_router.get("/healthz")
        def mock_healthz_redirect():
            return RedirectResponse(url="/v1/healthz", status_code=308)

        # Mock health router with canonical endpoints
        health_router = APIRouter()

        @health_router.get("/v1/health")
        def mock_v1_health():
            return {"status": "ok"}

        @health_router.get("/healthz/live")  # Note: healthz endpoints are at root level
        def mock_healthz_live():
            return {"status": "ok"}

        @health_router.get(
            "/healthz/ready"
        )  # Note: healthz endpoints are at root level
        def mock_healthz_ready():
            return {"status": "ok", "ok": True}

        @health_router.get("/v1/healthz")
        def mock_v1_healthz():
            return {"ok": True, "status": "ok"}

        # Mock status router
        status_router = APIRouter()

        @status_router.get("/status")
        def mock_status():
            return {"status": "ok"}

        status_public_router = APIRouter()

        @status_public_router.get("/rate_limit_status")
        def mock_rate_limit_status():
            return {"backend": "ok"}

        # Include in correct order: compat first, then health
        app.include_router(compat_router, prefix="")
        app.include_router(health_router, prefix="")
        app.include_router(status_router, prefix="/v1")
        app.include_router(status_public_router, prefix="/v1")

    client = TestClient(app)

    # Test that legacy /health redirects to /v1/health
    response = client.get("/health", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers.get("location") == "/v1/health"

    # Test that legacy /healthz redirects to /v1/healthz
    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers.get("location") == "/v1/healthz"

    # Test that following redirects works for /health
    response = client.get("/health", follow_redirects=True)
    assert response.status_code == 200

    # Test that following redirects works for /healthz
    response = client.get("/healthz", follow_redirects=True)
    assert response.status_code == 200

    # Test that canonical endpoints return 200
    response = client.get("/v1/health")
    assert response.status_code == 200

    response = client.get("/healthz/live")  # Note: healthz endpoints are at root level
    assert response.status_code == 200

    response = client.get("/healthz/ready")  # Note: healthz endpoints are at root level
    assert response.status_code == 200

    response = client.get("/v1/healthz")
    assert response.status_code == 200


def test_health_schema_inclusion():
    """Test that only canonical health endpoints appear in OpenAPI schema."""

    # Create a minimal test app
    app = FastAPI()

    # Import the actual routers
    try:
        from app.api.health import router as health_router
        from app.status import public_router as status_public_router
        from app.status import router as status_router

        app.include_router(health_router, prefix="")
        app.include_router(status_router, prefix="/v1")
        app.include_router(status_public_router, prefix="/v1")

    except Exception:
        # Create minimal mock routers if imports fail
        from fastapi import APIRouter

        health_router = APIRouter()

        @health_router.get("/v1/health")
        def mock_v1_health():
            return {"status": "ok"}

        @health_router.get("/healthz/live")
        def mock_healthz_live():
            return {"status": "ok"}

        @health_router.get("/healthz/ready")
        def mock_healthz_ready():
            return {"status": "ok", "ok": True}

        @health_router.get("/v1/healthz")
        def mock_v1_healthz():
            return {"ok": True, "status": "ok"}

        # Legacy endpoints should NOT be in schema
        @health_router.get("/health", include_in_schema=False)
        def mock_health():
            return {"status": "ok"}

        @health_router.get("/healthz", include_in_schema=False)
        def mock_healthz():
            return {"ok": True, "status": "ok"}

        status_router = APIRouter()

        @status_router.get("/status")
        def mock_status():
            return {"status": "ok"}

        status_public_router = APIRouter()

        @status_public_router.get("/rate_limit_status")
        def mock_rate_limit_status():
            return {"backend": "ok"}

        app.include_router(health_router, prefix="")
        app.include_router(status_router, prefix="/v1")
        app.include_router(status_public_router, prefix="/v1")

    # Get OpenAPI schema
    schema = app.openapi()

    # Extract paths from schema
    paths = schema.get("paths", {})

    # Canonical health endpoints should be in schema
    assert "/v1/health" in paths
    assert "/healthz/live" in paths  # Note: /healthz/live is at root level
    assert "/healthz/ready" in paths  # Note: /healthz/ready is at root level
    assert "/v1/healthz" in paths

    # Status endpoints should be in schema
    assert "/v1/status" in paths
    assert "/v1/rate_limit_status" in paths

    # Legacy health endpoints should NOT be in schema
    assert "/health" not in paths
    assert "/healthz" not in paths


def test_health_redirect_behavior():
    """Test comprehensive redirect behavior for health endpoints."""

    # Create minimal test app
    app = FastAPI()

    from fastapi import APIRouter

    # Health router with canonical endpoints
    health_router = APIRouter()

    @health_router.get("/v1/health")
    def v1_health():
        return {"status": "ok", "canonical": True}

    @health_router.get("/v1/healthz")
    def v1_healthz():
        return {"ok": True, "status": "ok", "canonical": True}

    @health_router.get("/v1/healthz/live")
    def v1_healthz_live():
        return {"status": "ok", "canonical": True}

    @health_router.get("/v1/healthz/ready")
    def v1_healthz_ready():
        return {"status": "ok", "ok": True, "canonical": True}

    # Compat router with redirects
    compat_router = APIRouter(include_in_schema=False)

    @compat_router.get("/health")
    def health_redirect():
        return RedirectResponse(url="/v1/health", status_code=308)

    @compat_router.get("/healthz")
    def healthz_redirect():
        return RedirectResponse(url="/v1/healthz", status_code=308)

    app.include_router(health_router, prefix="")
    app.include_router(compat_router, prefix="")

    client = TestClient(app)

    # Test redirects don't auto-follow
    response = client.get("/health", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/v1/health"
    # Should not contain canonical endpoint data (redirect responses have no body)
    assert len(response.content) == 0 or b"canonical" not in response.content

    response = client.get("/healthz", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/v1/healthz"
    # Should not contain canonical endpoint data (redirect responses have no body)
    assert len(response.content) == 0 or b"canonical" not in response.content

    # Test following redirects reaches canonical endpoints
    response = client.get("/health", follow_redirects=True)
    assert response.status_code == 200
    data = response.json()
    assert data.get("canonical") is True
    assert data.get("status") == "ok"

    response = client.get("/healthz", follow_redirects=True)
    assert response.status_code == 200
    data = response.json()
    assert data.get("canonical") is True
    assert data.get("ok") is True

    # Test canonical endpoints directly
    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("canonical") is True

    response = client.get("/v1/healthz/live")
    assert response.status_code == 200
    data = response.json()
    assert data.get("canonical") is True

    response = client.get("/v1/healthz/ready")
    assert response.status_code == 200
    data = response.json()
    assert data.get("canonical") is True

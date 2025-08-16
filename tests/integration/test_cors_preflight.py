from starlette.testclient import TestClient
from app.main import app


def _preflight(client, path: str):
    return client.options(
        path,
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-csrf-token",
        },
    )


def test_global_preflight_headers():
    client = TestClient(app)
    for p in ("/v1/ask", "/v1/care/alerts", "/v1/music", "/v1/tv/photos"):
        r = _preflight(client, p)
        assert r.status_code == 200  # FastAPI CORS middleware returns 200, not 204
        h = {k.lower(): v for k, v in r.headers.items()}
        assert h.get("access-control-allow-origin") == "http://127.0.0.1:3000"
        assert h.get("access-control-allow-credentials") == "true"
        assert "authorization" in h.get("access-control-allow-headers", "").lower()
        assert "content-type" in h.get("access-control-allow-headers", "").lower()
        assert "x-csrf-token" in h.get("access-control-allow-headers", "").lower()
        assert "post" in h.get("access-control-allow-methods", "").lower()
        assert h.get("access-control-max-age") == "600"
        assert "origin" in h.get("vary", "").lower()
        assert not any(k.lower().startswith("ratelimit-") for k in r.headers)


def test_preflight_no_rate_limit_headers():
    """Ensure no rate limit headers appear on OPTIONS preflight requests."""
    client = TestClient(app)
    for p in ("/v1/ask", "/v1/care/alerts", "/v1/music", "/v1/tv/photos"):
        r = _preflight(client, p)
        assert r.status_code == 200  # FastAPI CORS middleware returns 200, not 204
        # Check that no rate limit headers are present
        rate_limit_headers = [k for k in r.headers.keys() if k.lower().startswith("ratelimit-")]
        assert len(rate_limit_headers) == 0, f"Rate limit headers found: {rate_limit_headers}"


def test_preflight_no_auth_headers():
    """Ensure no auth-related headers appear on OPTIONS preflight requests."""
    client = TestClient(app)
    for p in ("/v1/ask", "/v1/care/alerts", "/v1/music", "/v1/tv/photos"):
        r = _preflight(client, p)
        assert r.status_code == 200  # FastAPI CORS middleware returns 200, not 204
        # Check that no auth-related headers are present
        auth_headers = [k for k in r.headers.keys() if k.lower() in ["www-authenticate", "authorization"]]
        assert len(auth_headers) == 0, f"Auth headers found: {auth_headers}"


def test_preflight_cors_headers_present():
    """Ensure all required CORS headers are present on OPTIONS preflight requests."""
    client = TestClient(app)
    for p in ("/v1/ask", "/v1/care/alerts", "/v1/music", "/v1/tv/photos"):
        r = _preflight(client, p)
        assert r.status_code == 200  # FastAPI CORS middleware returns 200, not 204
        h = {k.lower(): v for k, v in r.headers.items()}
        
        # Required CORS headers
        required_headers = [
            "access-control-allow-origin",
            "access-control-allow-credentials", 
            "access-control-allow-headers",
            "access-control-allow-methods",
            "access-control-max-age",
            "vary"
        ]
        
        for header in required_headers:
            assert header in h, f"Missing required CORS header: {header}"
        
        # Check specific values
        assert h["access-control-allow-origin"] == "http://127.0.0.1:3000"
        assert h["access-control-allow-credentials"] == "true"
        assert h["access-control-max-age"] == "600"
        assert "origin" in h["vary"].lower()


def test_regular_request_cors_headers():
    """Ensure CORS headers are present on regular requests."""
    client = TestClient(app)
    for p in ("/v1/ask", "/v1/care/alerts", "/v1/music", "/v1/tv/photos"):
        r = client.get(p, headers={"Origin": "http://127.0.0.1:3000"})
        h = {k.lower(): v for k, v in r.headers.items()}
        assert h.get("access-control-allow-origin") == "http://127.0.0.1:3000"
        assert h.get("access-control-allow-credentials") == "true"

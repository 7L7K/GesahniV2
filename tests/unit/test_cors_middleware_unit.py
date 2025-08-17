"""Test CORS-first middleware architecture.

This test suite verifies that the CORS middleware is properly configured as the outermost
middleware and that OPTIONS requests are handled correctly according to the rules:

1. CORS must be outermost
2. CORSMiddleware needs to be the last add_middleware(...) call
3. Every custom layer must be OPTIONS-agnostic
4. Middlewares, dependencies, guards, exception handlers, and any rate-limit libraries 
   must not add headers on OPTIONS
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_cors_is_outermost_middleware():
    """Test that CORS middleware is the outermost middleware."""
    # The middleware order should be printed during app startup
    # We can verify this by checking that OPTIONS requests are handled by CORS
    # before reaching custom middleware
    
    client = TestClient(app)
    
    # Test OPTIONS request with proper CORS headers
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # Should return 200 (success) with CORS headers
    assert response.status_code == 200
    
    # Should have CORS headers
    assert 'access-control-allow-origin' in response.headers
    assert 'access-control-allow-methods' in response.headers
    assert 'access-control-allow-headers' in response.headers
    assert 'access-control-allow-credentials' in response.headers
    
    # Should NOT have rate limit headers (custom middleware should not run)
    rate_limit_headers = [h for h in response.headers.keys() if 'rate' in h.lower() or 'limit' in h.lower()]
    assert not rate_limit_headers, f"OPTIONS response should not have rate limit headers: {rate_limit_headers}"


def test_options_requests_bypass_custom_middleware():
    """Test that OPTIONS requests bypass custom middleware and don't add custom headers."""
    client = TestClient(app)
    
    # Test OPTIONS request
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # Should return 200 (success)
    assert response.status_code == 200
    
    # Should have CORS headers
    assert 'access-control-allow-origin' in response.headers
    
    # Should NOT have rate limit headers
    assert 'ratelimit-limit' not in response.headers
    assert 'ratelimit-remaining' not in response.headers
    assert 'ratelimit-reset' not in response.headers
    assert 'X-RateLimit-Burst-Limit' not in response.headers
    assert 'X-RateLimit-Burst-Remaining' not in response.headers
    assert 'X-RateLimit-Burst-Reset' not in response.headers


def test_non_options_requests_get_rate_limit_headers():
    """Test that non-OPTIONS requests get rate limit headers from custom middleware."""
    client = TestClient(app)
    
    # Test POST request
    response = client.post('/v1/auth/logout')
    
    # Should return 204 (success)
    assert response.status_code == 204
    
    # Should have rate limit headers
    assert 'ratelimit-limit' in response.headers
    assert 'ratelimit-remaining' in response.headers
    assert 'ratelimit-reset' in response.headers
    assert 'X-RateLimit-Burst-Limit' in response.headers
    assert 'X-RateLimit-Burst-Remaining' in response.headers
    assert 'X-RateLimit-Burst-Reset' in response.headers


def test_cors_headers_are_present_for_all_origins():
    """Test that CORS headers are present for all configured origins."""
    client = TestClient(app)
    
    # Test with different origins
    origins = ['http://localhost:3000', 'http://127.0.0.1:3000']
    
    for origin in origins:
        response = client.options('/v1/auth/logout', headers={
            'Origin': origin,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type'
        })
        
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == origin


def test_cors_handles_preflight_requests_correctly():
    """Test that CORS handles preflight requests correctly."""
    client = TestClient(app)
    
    # Test preflight request with various headers
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type,x-csrf-token'
    })
    
    assert response.status_code == 200
    assert 'access-control-allow-origin' in response.headers
    assert 'access-control-allow-methods' in response.headers
    assert 'access-control-allow-headers' in response.headers
    assert 'access-control-max-age' in response.headers


def test_middleware_order_is_correct():
    """Test that middleware order is correct (CORS outermost)."""
    # This test verifies that the middleware order is correct by checking
    # that OPTIONS requests are handled by CORS before reaching custom middleware
    
    client = TestClient(app)
    
    # Test OPTIONS request
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # If CORS is outermost, it should handle OPTIONS and return 200
    # If custom middleware runs first, it might interfere
    assert response.status_code == 200
    
    # Should have CORS headers but no rate limit headers
    assert 'access-control-allow-origin' in response.headers
    assert 'ratelimit-limit' not in response.headers


def test_x_request_id_header_is_present():
    """Test that X-Request-ID header is present for non-OPTIONS requests, but not for OPTIONS requests."""
    client = TestClient(app)
    
    # Test OPTIONS request - should NOT have X-Request-ID (CORS short-circuits before middleware)
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # OPTIONS requests should NOT have X-Request-ID (CORS handles them before middleware)
    assert 'x-request-id' not in response.headers
    
    # Test POST request - should have X-Request-ID
    response = client.post('/v1/auth/logout')
    assert 'x-request-id' in response.headers


def test_cors_credentials_are_handled_correctly():
    """Test that CORS credentials are handled correctly."""
    client = TestClient(app)
    
    # Test OPTIONS request with credentials
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    assert response.status_code == 200
    assert response.headers['access-control-allow-credentials'] == 'true'


def test_cors_max_age_is_set():
    """Test that CORS max-age is set correctly."""
    client = TestClient(app)
    
    # Test OPTIONS request
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    assert response.status_code == 200
    assert 'access-control-max-age' in response.headers
    assert response.headers['access-control-max-age'] == '600'

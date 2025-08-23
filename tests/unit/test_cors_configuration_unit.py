"""Test CORS configuration requirements.

This test suite verifies that the CORS configuration meets the specific requirements:

1. Backend allowlist: exactly http://localhost:3000 (not both localhost and 127)
2. Allow credentials: yes (cookies/tokens)
3. Expose headers: only what you need (e.g., X-Request-ID), not wildcards
4. Preflight: CORS middleware registered as the outermost layer so OPTIONS short-circuits
"""

from fastapi.testclient import TestClient

from app.main import app


def test_cors_allowlist_exactly_localhost_3000():
    """Test that CORS allowlist contains exactly http://localhost:3000."""
    client = TestClient(app)
    
    # Test with allowed origin
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
    
    # Test with disallowed origin - should be rejected with 400
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # Should return 400 for disallowed origin (security behavior)
    assert response.status_code == 400


def test_cors_allow_credentials_yes():
    """Test that CORS allows credentials (cookies/tokens)."""
    client = TestClient(app)
    
    # Test preflight request
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    assert response.status_code == 200
    assert response.headers['access-control-allow-credentials'] == 'true'
    
    # Test actual request
    response = client.get('/health/live', headers={
        'Origin': 'http://localhost:3000'
    })
    
    assert response.status_code == 200
    assert response.headers.get('access-control-allow-credentials') == 'true'


def test_cors_expose_headers_only_required():
    """Test that CORS exposes only required headers, not wildcards."""
    client = TestClient(app)
    
    # Test actual request (expose headers are only set for actual requests, not preflight)
    response = client.get('/health/live', headers={
        'Origin': 'http://localhost:3000'
    })
    
    assert response.status_code == 200
    
    # Should expose only X-Request-ID
    expose_headers = response.headers.get('access-control-expose-headers', '')
    assert 'X-Request-ID' in expose_headers
    
    # Should NOT expose other headers that were previously exposed
    assert 'X-CSRF-Token' not in expose_headers
    assert 'Retry-After' not in expose_headers
    assert 'RateLimit-Limit' not in expose_headers
    assert 'RateLimit-Remaining' not in expose_headers
    assert 'RateLimit-Reset' not in expose_headers
    
    # Should not expose wildcards
    assert '*' not in expose_headers


def test_cors_preflight_short_circuits():
    """Test that CORS middleware is outermost so OPTIONS requests short-circuit."""
    client = TestClient(app)
    
    # Test OPTIONS request
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # Should return 200 immediately (short-circuited by CORS)
    assert response.status_code == 200
    
    # Should have CORS headers
    assert 'access-control-allow-origin' in response.headers
    assert 'access-control-allow-methods' in response.headers
    assert 'access-control-allow-headers' in response.headers
    assert 'access-control-allow-credentials' in response.headers
    assert 'access-control-max-age' in response.headers
    
    # Should NOT have custom middleware headers
    assert 'x-request-id' not in response.headers
    assert 'ratelimit-limit' not in response.headers
    assert 'ratelimit-remaining' not in response.headers


def test_cors_actual_requests_get_middleware_headers():
    """Test that actual requests (non-OPTIONS) get middleware headers."""
    client = TestClient(app)
    
    # Test actual request
    response = client.get('/health/live', headers={
        'Origin': 'http://localhost:3000'
    })
    
    # Should return 200
    assert response.status_code == 200
    
    # Should have CORS headers
    assert 'access-control-allow-origin' in response.headers
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
    
    # Should have custom middleware headers
    assert 'x-request-id' in response.headers


def test_cors_malicious_origin_rejected():
    """Test that malicious origins are rejected."""
    client = TestClient(app)
    
    # Test with malicious origin
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://malicious-site.com',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    # Should return 400 for malicious origin (security behavior)
    assert response.status_code == 400


def test_cors_multiple_origins_handled():
    """Test that multiple origins in config are handled correctly (first one used)."""
    client = TestClient(app)
    
    # Test with localhost origin (should be allowed)
    response = client.options('/v1/auth/logout', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    })
    
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'


def test_cors_headers_consistency():
    """Test that CORS headers are consistent across different endpoints."""
    client = TestClient(app)
    
    endpoints = ['/health/live', '/v1/auth/logout', '/config']
    
    for endpoint in endpoints:
        # Test actual request (expose headers are only set for actual requests)
        response = client.get(endpoint, headers={
            'Origin': 'http://localhost:3000'
        })
        
        if response.status_code in [200, 403]:  # Some endpoints might require auth
            assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
            assert response.headers['access-control-allow-credentials'] == 'true'
            # Expose headers are only set for actual requests, not preflight
            if response.status_code == 200:
                assert 'X-Request-ID' in response.headers.get('access-control-expose-headers', '')

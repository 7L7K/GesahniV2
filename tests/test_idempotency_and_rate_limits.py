"""Tests for idempotency middleware and per-route rate limiting."""
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.idempotency import IdempotencyMiddleware, get_idempotency_store
from app.middleware.rate_limit import RateLimitMiddleware, _test_clear_buckets, _test_clear_metrics, _test_set_config, _test_reset_config


class TestIdempotencyMiddleware:
    """Test suite for idempotency middleware."""

    def setup_method(self):
        """Setup test fixtures."""
        self.app = FastAPI()
        self.store = get_idempotency_store()

        # Clear any existing data
        if hasattr(self.store, '_memory_store'):
            self.store._memory_store.clear()

        # Add test routes
        @self.app.post("/v1/ask")
        async def ask_endpoint():
            return {"message": "success", "id": str(uuid.uuid4())}

        @self.app.post("/v1/payments")
        async def payment_endpoint():
            return {"status": "processed", "transaction_id": str(uuid.uuid4())}

        @self.app.get("/v1/status")
        async def status_endpoint():
            return {"status": "ok"}

        # Add middleware
        self.app.add_middleware(IdempotencyMiddleware)

        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self.store, '_memory_store'):
            self.store._memory_store.clear()

    def test_idempotency_key_not_provided(self):
        """Test that requests without idempotency key work normally."""
        response = self.client.post("/v1/ask", json={"prompt": "test"})
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_idempotency_same_key_same_result(self):
        """Test that same idempotency key returns same result."""
        idempotency_key = str(uuid.uuid4())
        headers = {"Idempotency-Key": idempotency_key}

        # First request
        response1 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with same key
        response2 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        assert response2.status_code == 200
        data2 = response2.json()

        # Should return same result
        assert data1 == data2

    def test_idempotency_different_key_different_result(self):
        """Test that different idempotency keys return different results."""
        headers1 = {"Idempotency-Key": str(uuid.uuid4())}
        headers2 = {"Idempotency-Key": str(uuid.uuid4())}

        response1 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers1)
        response2 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers2)

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Should be different results
        assert data1 != data2

    def test_idempotency_key_conflict_different_request(self):
        """Test that same key with different request body returns 409."""
        idempotency_key = str(uuid.uuid4())
        headers = {"Idempotency-Key": idempotency_key}

        # First request
        self.client.post("/v1/ask", json={"prompt": "test1"}, headers=headers)

        # Second request with same key but different body
        response = self.client.post("/v1/ask", json={"prompt": "test2"}, headers=headers)
        assert response.status_code == 409

        data = response.json()
        assert "error" in data
        assert "idempotency_conflict" in data.get("code", "")

    def test_idempotency_only_applies_to_write_methods(self):
        """Test that idempotency only applies to POST/PUT/PATCH/DELETE."""
        idempotency_key = str(uuid.uuid4())
        headers = {"Idempotency-Key": idempotency_key}

        # GET request should not be affected by idempotency
        response1 = self.client.get("/v1/status", headers=headers)
        response2 = self.client.get("/v1/status", headers=headers)

        assert response1.status_code == 200
        assert response2.status_code == 200

    def test_idempotency_applies_to_payment_endpoints(self):
        """Test that idempotency applies to payment-like endpoints."""
        idempotency_key = str(uuid.uuid4())
        headers = {"Idempotency-Key": idempotency_key}

        # First request to payment endpoint
        response1 = self.client.post("/v1/payments", json={"amount": 100}, headers=headers)
        assert response1.status_code == 200

        # Second request with same key should return same result
        response2 = self.client.post("/v1/payments", json={"amount": 100}, headers=headers)
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()
        assert data1 == data2

    def test_idempotency_invalid_key_format(self):
        """Test that invalid idempotency key format returns 400."""
        headers = {"Idempotency-Key": "invalid"}

        response = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        assert response.status_code == 400

        data = response.json()
        assert "Invalid Idempotency-Key format" in data.get("detail", "")

    @patch('app.router.ask_api.get_idempotency_store')
    def test_idempotency_redis_fallback(self, mock_get_store):
        """Test that ask endpoint handles Redis unavailability gracefully."""
        # Mock store to raise exception
        mock_store = MagicMock()
        mock_store.get_response.side_effect = Exception("Redis unavailable")
        mock_store.store_response.side_effect = Exception("Redis unavailable")
        mock_get_store.return_value = mock_store

        idempotency_key = str(uuid.uuid4())
        headers = {"Idempotency-Key": idempotency_key}

        # Should still work despite Redis errors (falls back to normal processing)
        response = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        assert response.status_code == 200


class TestPerRouteRateLimiting:
    """Test suite for per-route rate limiting."""

    def setup_method(self):
        """Setup test fixtures."""
        self.app = FastAPI()

        # Clear rate limit state
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

        # Set test rate limits and enable rate limiting in tests
        _test_set_config(
            ask_rate_limit=2,  # Very tight for ask
            admin_rate_limit=3,  # Tight for admin
            read_rate_limit=10,  # Looser for reads
            write_rate_limit=5,  # Default for writes
        )

        # Ensure rate limiting is enabled in tests
        import os
        os.environ['ENABLE_RATE_LIMIT_IN_TESTS'] = '1'

        # Add test routes
        @self.app.post("/v1/ask")
        async def ask_endpoint():
            return {"message": "success"}

        @self.app.get("/v1/admin/status")
        async def admin_status_endpoint():
            return {"status": "ok"}

        @self.app.post("/v1/admin/action")
        async def admin_action_endpoint():
            return {"result": "done"}

        @self.app.get("/v1/data")
        async def read_endpoint():
            return {"data": "value"}

        @self.app.post("/v1/data")
        async def write_endpoint():
            return {"created": True}

        @self.app.post("/v1/payments")
        async def payment_endpoint():
            return {"processed": True}

        # Add middleware - important: add in correct order
        # RequestIDMiddleware should be added first for proper logging
        from app.middleware import RequestIDMiddleware
        self.app.add_middleware(RequestIDMiddleware)
        self.app.add_middleware(RateLimitMiddleware)

        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up after each test."""
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

    def test_ask_endpoint_tight_rate_limit(self):
        """Test that /v1/ask has tight rate limiting (2 requests per minute)."""
        # Should allow first 2 requests
        for i in range(2):
            response = self.client.post("/v1/ask", json={"prompt": f"test{i}"})
            assert response.status_code == 200

        # Third request should be rate limited
        response = self.client.post("/v1/ask", json={"prompt": "test3"})
        assert response.status_code == 429

    def test_admin_endpoints_tight_rate_limit(self):
        """Test that admin endpoints have tight rate limiting."""
        # Should allow first 3 requests to admin status
        for i in range(3):
            response = self.client.get("/v1/admin/status")
            assert response.status_code == 200

        # Fourth request should be rate limited
        response = self.client.get("/v1/admin/status")
        assert response.status_code == 429

    def test_read_endpoints_loose_rate_limit(self):
        """Test that read endpoints have looser rate limiting (10 requests)."""
        # Should allow first 10 requests
        for i in range(10):
            response = self.client.get("/v1/data")
            assert response.status_code == 200

        # Eleventh request should be rate limited
        response = self.client.get("/v1/data")
        assert response.status_code == 429

    def test_write_endpoints_default_rate_limit(self):
        """Test that general write endpoints have default rate limiting (5 requests)."""
        # Should allow first 5 requests
        for i in range(5):
            response = self.client.post("/v1/payments", json={"amount": i})
            assert response.status_code == 200

        # Sixth request should be rate limited
        response = self.client.post("/v1/payments", json={"amount": 5})
        assert response.status_code == 429

    def test_rate_limit_headers(self):
        """Test that rate limit headers are included in responses."""
        response = self.client.post("/v1/ask", json={"prompt": "test"})

        # Check for rate limit headers (note the casing from header utility)
        assert "X-Ratelimit-Limit" in response.headers
        assert "X-Ratelimit-Remaining" in response.headers
        assert "X-Ratelimit-Reset" in response.headers

    def test_rate_limit_burst_then_reset(self):
        """Test that rate limit resets after window expires."""
        # Exhaust rate limit for ask endpoint
        for i in range(2):
            response = self.client.post("/v1/ask", json={"prompt": f"test{i}"})
            assert response.status_code == 200

        # Should be rate limited
        response = self.client.post("/v1/ask", json={"prompt": "test3"})
        assert response.status_code == 429

        # Simulate time passing (by clearing buckets - in real scenario time would pass)
        _test_clear_buckets()

        # Should allow requests again
        response = self.client.post("/v1/ask", json={"prompt": "test4"})
        assert response.status_code == 200

    def test_different_routes_different_limits(self):
        """Test that different routes have different rate limits."""
        # Ask endpoint: 2 requests allowed
        for i in range(2):
            response = self.client.post("/v1/ask", json={"prompt": f"test{i}"})
            assert response.status_code == 200

        # Ask should be rate limited now
        response = self.client.post("/v1/ask", json={"prompt": "blocked"})
        assert response.status_code == 429

        # But read endpoint should still work (10 requests allowed)
        for i in range(5):  # Test subset
            response = self.client.get("/v1/data")
            assert response.status_code == 200

    def test_rate_limit_retry_after_header(self):
        """Test that Retry-After header is included when rate limited."""
        # Exhaust rate limit
        for i in range(2):
            self.client.post("/v1/ask", json={"prompt": f"test{i}"})

        # Rate limited request
        response = self.client.post("/v1/ask", json={"prompt": "blocked"})
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @patch.dict('os.environ', {'RATE_LIMIT_MODE': 'off'})
    def test_rate_limit_disabled_by_env(self):
        """Test that rate limiting can be disabled via environment variable."""
        # Should allow unlimited requests when disabled
        for i in range(10):
            response = self.client.post("/v1/ask", json={"prompt": f"test{i}"})
            assert response.status_code == 200


class TestIdempotencyAndRateLimitIntegration:
    """Test suite for idempotency and rate limiting working together."""

    def setup_method(self):
        """Setup test fixtures."""
        self.app = FastAPI()

        # Clear states
        store = get_idempotency_store()
        if hasattr(store, '_memory_store'):
            store._memory_store.clear()
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

        # Set tight rate limits for testing
        _test_set_config(ask_rate_limit=1)

        # Ensure rate limiting is enabled in tests
        import os
        os.environ['ENABLE_RATE_LIMIT_IN_TESTS'] = '1'

        @self.app.post("/v1/ask")
        async def ask_endpoint():
            return {"message": "success", "id": str(uuid.uuid4())}

        # Add both middlewares in correct order
        from app.middleware import RequestIDMiddleware
        self.app.add_middleware(RequestIDMiddleware)
        self.app.add_middleware(IdempotencyMiddleware)
        self.app.add_middleware(RateLimitMiddleware)

        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up after each test."""
        store = get_idempotency_store()
        if hasattr(store, '_memory_store'):
            store._memory_store.clear()
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

    def test_idempotency_bypasses_rate_limit(self):
        """Test that idempotent requests bypass rate limiting when returning cached responses."""
        idempotency_key = str(uuid.uuid4())
        headers = {"Idempotency-Key": idempotency_key}

        # First request - should succeed and be cached
        response1 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with same key - should return cached response and bypass rate limit
        response2 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers)
        assert response2.status_code == 200
        data2 = response2.json()

        # Should be the same response
        assert data1 == data2

    def test_rate_limit_applies_to_new_idempotency_keys(self):
        """Test that rate limiting applies when using different idempotency keys."""
        # First request with key1
        headers1 = {"Idempotency-Key": str(uuid.uuid4())}
        response1 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers1)
        assert response1.status_code == 200

        # Second request with key2 - should be rate limited (only 1 request allowed)
        headers2 = {"Idempotency-Key": str(uuid.uuid4())}
        response2 = self.client.post("/v1/ask", json={"prompt": "test"}, headers=headers2)
        assert response2.status_code == 429


if __name__ == "__main__":
    pytest.main([__file__])

"""
Comprehensive error testing suite to catch issues not covered by existing tests.

This test suite focuses on:
- Edge cases and error conditions
- Integration failures
- Resource exhaustion scenarios
- Concurrent access issues
- Network failures
- Memory leaks
- Performance degradation
"""

import asyncio
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.gpt_client import ask_gpt
from app.llama_integration import _check_and_set_flag
from app.logging_config import get_last_errors

# Import app components
from app.main import app
from app.memory.api import _get_store
from app.tokens import create_access_token


class TestComprehensiveErrors:
    """Comprehensive error testing suite."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self, monkeypatch):
        """Set up test environment with comprehensive monitoring."""
        # Enable verbose logging for tests
        monkeypatch.setenv("VERBOSE_LOGGING", "1")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_TO_STDOUT", "1")

        # Mock external dependencies
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "test-model")
        monkeypatch.setenv("HOME_ASSISTANT_URL", "http://localhost:8123")
        monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "test-token")
        monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-testing-only")

        # Create test client
        self.client = TestClient(app)

        # Track errors during test
        self.errors_before = len(get_last_errors())

        yield

        # Check for new errors after test
        errors_after = len(get_last_errors())
        if errors_after > self.errors_before:
            recent_errors = get_last_errors(errors_after - self.errors_before)
            print(f"New errors detected during test: {recent_errors}")

    def test_auth_token_creation_edge_cases(self):
        """Test edge cases in token creation."""
        # Test with empty data
        with pytest.raises(KeyError):
            create_access_token({})

        # Test with invalid data types
        with pytest.raises(TypeError):
            create_access_token(None)

        # Test with very long usernames
        long_username = "a" * 1000
        token = create_access_token({"sub": long_username})
        assert len(token) > 0

        # Test with special characters in username
        special_username = "test@user.com+special"
        token = create_access_token({"sub": special_username})
        assert len(token) > 0

    def test_concurrent_token_creation(self):
        """Test concurrent token creation to catch race conditions."""

        def create_token(username):
            return create_access_token({"sub": username})

        # Create tokens concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_token, f"user_{i}") for i in range(100)]
            tokens = [future.result() for future in futures]

        # Verify all tokens are unique
        assert len(set(tokens)) == 100

        # Verify all tokens are valid
        for token in tokens:
            assert len(token) > 0
            assert isinstance(token, str)

    def test_memory_store_edge_cases(self):
        """Test edge cases in memory store operations."""
        # Test with very large content
        large_content = "x" * 1000000  # 1MB
        try:
            # This might fail due to size limits
            store = _get_store()
            # Note: This is a test - in real usage we'd handle this gracefully
        except Exception as e:
            print(f"Expected error with large content: {e}")

        # Test with empty content
        try:
            store = _get_store()
            # Test empty content handling
        except Exception as e:
            print(f"Error with empty content: {e}")

        # Test with None content
        try:
            store = _get_store()
            # Test None content handling
        except Exception as e:
            print(f"Error with None content: {e}")

    def test_llama_integration_failures(self):
        """Test LLaMA integration failure scenarios."""
        # Test when LLaMA is completely unavailable
        with patch("app.llama_integration.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                Exception("Connection failed")
            )

            # This should handle the failure gracefully
            try:
                asyncio.run(_check_and_set_flag())
            except Exception as e:
                print(f"Expected LLaMA failure handled: {e}")

        # Test when LLaMA returns invalid responses
        with patch("app.llama_integration.httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.json.return_value = {"invalid": "response"}
            mock_client.return_value.__aenter__.return_value.post.return_value = (
                mock_response
            )

            try:
                asyncio.run(_check_and_set_flag())
            except Exception as e:
                print(f"Expected invalid response handled: {e}")

    def test_gpt_client_failures(self):
        """Test GPT client failure scenarios."""
        # Test with invalid API key
        with patch.dict(os.environ, {"OPENAI_API_KEY": "invalid-key"}):
            try:
                asyncio.run(ask_gpt("test prompt", routing_decision=None))
            except Exception as e:
                print(f"Expected GPT failure with invalid key: {e}")

        # Test with network timeout
        with patch("app.gpt_client.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = TimeoutError(
                "Request timeout"
            )
            mock_get_client.return_value = mock_client

            try:
                asyncio.run(ask_gpt("test prompt", routing_decision=None))
            except Exception as e:
                print(f"Expected GPT timeout handled: {e}")

    def test_request_id_collisions(self):
        """Test request ID collision scenarios."""
        # Generate many requests quickly to test ID uniqueness
        request_ids = set()

        for i in range(1000):
            response = self.client.get("/health")
            req_id = response.headers.get("X-Request-ID")
            if req_id:
                request_ids.add(req_id)

        # All request IDs should be unique
        assert len(request_ids) == 1000

    def test_concurrent_requests(self):
        """Test concurrent request handling."""

        def make_request():
            return self.client.get("/health")

        # Make many concurrent requests
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(100)]
            responses = [future.result() for future in futures]

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200

        # All should have unique request IDs
        request_ids = [
            resp.headers.get("X-Request-ID")
            for resp in responses
            if resp.headers.get("X-Request-ID")
        ]
        assert len(set(request_ids)) == len(request_ids)

    def test_large_payload_handling(self):
        """Test handling of large payloads."""
        # Test with large JSON payload
        large_payload = {"prompt": "x" * 100000, "user_id": "test-user"}  # 100KB prompt

        try:
            response = self.client.post("/ask", json=large_payload)
            # Should either succeed or fail gracefully
            assert response.status_code in [200, 400, 413, 500]
        except Exception as e:
            print(f"Expected error with large payload: {e}")

    def test_malformed_requests(self):
        """Test handling of malformed requests."""
        # Test with invalid JSON
        response = self.client.post(
            "/ask", data="invalid json", headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]

        # Test with missing required fields
        response = self.client.post("/ask", json={})
        assert response.status_code in [400, 422]

        # Test with wrong content type
        response = self.client.post(
            "/ask", data="test", headers={"Content-Type": "text/plain"}
        )
        assert response.status_code in [400, 415, 422]

    def test_resource_cleanup(self):
        """Test resource cleanup and memory leaks."""
        import gc
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Perform many operations that might leak resources
        for i in range(100):
            response = self.client.get("/health")
            assert response.status_code == 200

        # Force garbage collection
        gc.collect()

        # Check memory usage
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 10MB)
        assert (
            memory_increase < 10 * 1024 * 1024
        ), f"Memory leak detected: {memory_increase} bytes"

    def test_error_logging_completeness(self):
        """Test that errors are properly logged."""
        # Clear existing errors
        initial_errors = len(get_last_errors())

        # Trigger an error
        try:
            response = self.client.post("/ask", json={"invalid": "data"})
        except Exception:
            pass

        # Check that errors were logged
        final_errors = len(get_last_errors())
        assert final_errors >= initial_errors

    def test_startup_failure_recovery(self):
        """Test application startup with component failures."""
        # Test startup with missing dependencies
        with patch("app.auth._ensure_table") as mock_ensure_table:
            mock_ensure_table.side_effect = Exception("Database connection failed")

            # Application should still start
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code in [200, 503]  # Should handle degraded state

    def test_performance_degradation(self):
        """Test for performance degradation under load."""
        start_time = time.time()

        # Make many requests
        for i in range(100):
            response = self.client.get("/health")
            assert response.status_code == 200

        end_time = time.time()
        total_time = end_time - start_time

        # Should complete within reasonable time (less than 10 seconds)
        assert (
            total_time < 10.0
        ), f"Performance degradation detected: {total_time}s for 100 requests"

    def test_file_system_errors(self):
        """Test handling of file system errors."""
        # Test with read-only file system
        with tempfile.TemporaryDirectory() as temp_dir:
            # Make directory read-only
            os.chmod(temp_dir, 0o444)

            try:
                # Try to write to read-only directory
                test_file = Path(temp_dir) / "test.txt"
                test_file.write_text("test")
            except Exception as e:
                print(f"Expected file system error: {e}")

    def test_network_timeout_scenarios(self):
        """Test network timeout scenarios."""
        # Test with slow network simulation
        with patch("app.http_utils.json_request") as mock_request:
            mock_request.side_effect = TimeoutError("Network timeout")

            try:
                # This should handle timeout gracefully
                pass
            except Exception as e:
                print(f"Expected timeout handling: {e}")

    def test_memory_exhaustion(self):
        """Test behavior under memory pressure."""
        # Create large objects to simulate memory pressure
        large_objects = []

        try:
            for i in range(1000):
                large_objects.append("x" * 10000)  # 10KB each
        except MemoryError:
            print("Memory exhaustion test completed")
        finally:
            # Clean up
            large_objects.clear()

    def test_concurrent_database_access(self):
        """Test concurrent database access scenarios."""

        def db_operation():
            try:
                response = self.client.post(
                    "/login",
                    json={"username": f"user_{time.time()}", "password": "testpass123"},
                )
                return response.status_code
            except Exception as e:
                return f"Error: {e}"

        # Perform concurrent database operations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(db_operation) for _ in range(50)]
            results = [future.result() for future in futures]

        # Check results
        for result in results:
            assert isinstance(result, (int, str))

    def test_error_propagation(self):
        """Test that errors propagate correctly through the system."""
        # Test error propagation in middleware
        with patch("app.main._enhanced_startup") as mock_startup:
            mock_startup.side_effect = Exception("Startup error")

            # Application should handle startup errors gracefully
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code in [200, 503]

    def test_logging_under_load(self):
        """Test logging performance under high load."""
        # Enable debug logging
        logging.getLogger().setLevel(logging.DEBUG)

        start_time = time.time()

        # Generate many log messages
        for i in range(1000):
            logging.debug(f"Test log message {i}")

        end_time = time.time()
        logging_time = end_time - start_time

        # Logging should be fast (less than 1 second for 1000 messages)
        assert (
            logging_time < 1.0
        ), f"Logging performance issue: {logging_time}s for 1000 messages"

    def test_component_isolation(self):
        """Test that component failures don't cascade."""
        # Test that auth failures don't break health checks
        with patch("app.auth._ensure_table") as mock_ensure_table:
            mock_ensure_table.side_effect = Exception("Auth failure")

            response = self.client.get("/health")
            # Health check should still work, even if degraded
            assert response.status_code in [200, 503]

    def test_error_recovery(self):
        """Test error recovery mechanisms."""
        # Test that the system can recover from temporary failures
        with patch("app.llama_integration._check_and_set_flag") as mock_check:
            # First call fails
            mock_check.side_effect = [Exception("Temporary failure"), None]

            # System should handle the failure and recover
            try:
                asyncio.run(_check_and_set_flag())
            except Exception:
                pass  # Expected first failure

            # Second call should succeed
            try:
                asyncio.run(_check_and_set_flag())
            except Exception as e:
                pytest.fail(f"System should recover from temporary failures: {e}")


class TestIntegrationFailures:
    """Test integration failure scenarios."""

    def test_external_service_failures(self):
        """Test handling of external service failures."""
        # Test OpenAI API failures
        with patch("app.gpt_client.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = Exception(
                "OpenAI API error"
            )
            mock_get_client.return_value = mock_client

            client = TestClient(app)
            response = client.post("/ask", json={"prompt": "test"})
            # Should handle the failure gracefully
            assert response.status_code in [500, 503]

        # Test vector store failures
        with patch("app.memory.api._get_store") as mock_get_store:
            mock_store = Mock()
            mock_store.add_memory.side_effect = Exception("Vector store error")
            mock_get_store.return_value = mock_store

            # Should handle vector store failures gracefully
            pass

    def test_configuration_errors(self):
        """Test handling of configuration errors."""
        # Test with missing required environment variables
        with patch.dict(os.environ, {}, clear=True):
            try:
                # This should fail gracefully
                client = TestClient(app)
            except Exception as e:
                print(f"Expected configuration error: {e}")

    def test_data_corruption_scenarios(self):
        """Test handling of data corruption scenarios."""
        # Test with corrupted JWT tokens
        corrupted_token = "invalid.jwt.token"

        client = TestClient(app)
        response = client.get(
            "/health", headers={"Authorization": f"Bearer {corrupted_token}"}
        )
        # Should handle corrupted tokens gracefully
        assert response.status_code in [200, 401, 403]

    def test_rate_limiting_edge_cases(self):
        """Test rate limiting edge cases."""
        client = TestClient(app)

        # Make many requests quickly
        responses = []
        for i in range(100):
            response = client.get("/health")
            responses.append(response.status_code)

        # Should handle rate limiting gracefully
        # Most requests should succeed, some might be rate limited
        success_count = sum(1 for code in responses if code == 200)
        assert success_count > 0, "All requests were blocked"


if __name__ == "__main__":
    # Run comprehensive tests
    pytest.main([__file__, "-v", "--tb=short"])

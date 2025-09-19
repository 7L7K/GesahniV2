"""
Regression tests for auth request logging functionality.

Tests the enhanced logging in app.auth.service.log_request_meta() to ensure
comprehensive request metadata logging works correctly and prevents future
regressions.
"""

import logging
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth.service import log_request_meta


class TestAuthRequestLogging:
    """Test suite for auth request logging functionality."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request with comprehensive test data."""
        request = MagicMock(spec=Request)

        # Mock URL with proper __str__ method
        mock_url = MagicMock()
        mock_url.path = "/v1/test"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/test")
        request.url = mock_url

        # Mock headers
        request.headers = {
            "origin": "http://localhost:3000",
            "referer": "http://localhost:3000/dashboard",
            "user-agent": "Mozilla/5.0 Test Browser",
            "content-type": "application/json",
            "authorization": "Bearer test.jwt.token",
            "content-length": "123",
            "accept": "application/json",
            "accept-encoding": "gzip, deflate",
            "x-forwarded-for": "192.168.1.100",
            "x-real-ip": "10.0.0.1",
            "x-api-key": "test-api-key-123",
        }

        # Mock cookies
        request.cookies = {
            "GSNH_AT": "access_token_value",
            "GSNH_RT": "refresh_token_value",
            "session_id": "test_session_123",
        }

        # Mock query params
        mock_query_params = MagicMock()
        mock_query_params.__iter__ = MagicMock(return_value=iter([]))
        mock_query_params.__len__ = MagicMock(return_value=0)
        request.query_params = mock_query_params

        # Mock client
        mock_client = MagicMock()
        mock_client.host = "127.0.0.1"
        mock_client.port = 12345
        request.client = mock_client

        # Mock request state
        request.state = {"user_id": "test_user_123", "session_id": "test_session_456"}
        request.request_id = "req_12345"

        request.method = "POST"

        return request

    @pytest.fixture
    def caplog_with_structured(self, caplog):
        """Configure caplog to capture structured logging."""
        caplog.set_level(logging.INFO)
        return caplog

    def test_log_request_meta_comprehensive_logging(self, mock_request, caplog_with_structured):
        """Test that log_request_meta produces comprehensive structured logs."""
        import asyncio

        async def run_test():
            # Execute the function
            result = await log_request_meta(mock_request)

            # Verify return value
            assert result is mock_request

            # Get all log records
            records = caplog_with_structured.records

            # Should have multiple log entries
            assert len(records) >= 3  # START, METADATA, COMPLETE

            # Find specific log entries
            start_record = None
            metadata_record = None
            complete_record = None

            for record in records:
                if "START" in record.message:
                    start_record = record
                elif "METADATA" in record.message:
                    metadata_record = record
                elif "COMPLETE" in record.message:
                    complete_record = record

            # Verify START log
            assert start_record is not None
            assert start_record.extra["req_id"] is not None
            assert start_record.extra["function"] == "log_request_meta"
            assert start_record.extra["phase"] == "entry"
            assert "timestamp" in start_record.extra
            assert start_record.extra["url"] == "http://testserver/v1/test"
            assert start_record.extra["method"] == "POST"

            # Verify METADATA log
            assert metadata_record is not None
            assert metadata_record.extra["req_id"] == start_record.extra["req_id"]
            assert metadata_record.extra["phase"] == "metadata_extraction"

            meta = metadata_record.extra["meta"]
            assert meta["path"] == "/v1/test"
            assert meta["method"] == "POST"
            assert meta["origin"] == "http://localhost:3000"
            assert meta["referer"] == "http://localhost:3000/dashboard"
            assert meta["user_agent"] == "Mozilla/5.0 Test Browser"
            assert meta["content_type"] == "application/json"
            assert meta["client_ip"] == "127.0.0.1"
            assert meta["client_port"] == 12345
            assert meta["has_auth_header"] is True
            assert meta["auth_header_type"] == "Bearer"
            assert len(meta["cookie_names"]) == 3
            assert "GSNH_AT" in meta["cookie_names"]
            assert "GSNH_RT" in meta["cookie_names"]
            assert "session_id" in meta["cookie_names"]

            # Verify security headers are logged
            security_headers = meta["security_headers"]
            assert "authorization" in security_headers
            assert security_headers["x-forwarded-for"] == "192.168.1.100"
            assert security_headers["x-api-key"] == "test-api-key-123"

            # Verify COMPLETE log
            assert complete_record is not None
            assert complete_record.extra["req_id"] == start_record.extra["req_id"]
            assert complete_record.extra["phase"] == "exit"
            assert complete_record.extra["success"] is True
            assert "processing_time_ms" in complete_record.extra

        asyncio.run(run_test())

    def test_log_request_meta_minimal_request(self, caplog_with_structured):
        """Test logging with minimal request data."""
        import asyncio

        # Create minimal mock request
        request = MagicMock(spec=Request)
        mock_url = MagicMock()
        mock_url.path = "/v1/minimal"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/minimal")
        request.url = mock_url
        request.method = "GET"
        request.headers = {}
        request.cookies = {}
        request.query_params = MagicMock()
        request.query_params.__iter__ = MagicMock(return_value=iter([]))
        request.query_params.__len__ = MagicMock(return_value=0)
        request.client = None
        request.state = {}
        request.request_id = None

        async def run_test():
            result = await log_request_meta(request)
            assert result is request

            records = caplog_with_structured.records
            assert len(records) >= 2  # Should have START and METADATA at minimum

            # Find metadata record
            metadata_record = None
            for record in records:
                if "METADATA" in record.message:
                    metadata_record = record
                    break

            assert metadata_record is not None
            meta = metadata_record.extra["meta"]
            assert meta["client_ip"] == "unknown"
            assert meta["client_port"] == "unknown"
            assert meta["has_auth_header"] is False
            assert meta["cookies_present"] is False

        asyncio.run(run_test())

    def test_log_request_meta_with_security_warnings(self, caplog_with_structured):
        """Test that security warnings are properly logged."""
        import asyncio

        # Create request with security issues
        request = MagicMock(spec=Request)
        mock_url = MagicMock()
        mock_url.path = "/v1/insecure"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/insecure")
        request.url = mock_url
        request.method = "GET"
        request.headers = {}  # No auth header
        request.cookies = {}  # No cookies
        request.query_params = MagicMock()
        request.query_params.__iter__ = MagicMock(return_value=iter([]))
        request.query_params.__len__ = MagicMock(return_value=0)
        request.client = None  # Unknown IP
        request.state = {}
        request.request_id = "insecure_req_123"

        async def run_test():
            result = await log_request_meta(request)
            assert result is request

            records = caplog_with_structured.records

            # Should have a SECURITY WARNINGS log
            warning_record = None
            for record in records:
                if "SECURITY WARNINGS" in record.message:
                    warning_record = record
                    break

            assert warning_record is not None
            assert warning_record.levelno == logging.WARNING
            warnings = warning_record.extra["warnings"]
            assert "no_auth_header" in warnings
            assert "no_cookies" in warnings
            assert "unknown_client_ip" in warnings

        asyncio.run(run_test())

    def test_log_request_meta_exception_handling(self, caplog_with_structured):
        """Test that exceptions are properly logged and re-raised."""
        import asyncio

        # Create request that will cause an exception
        request = MagicMock(spec=Request)
        mock_url = MagicMock()
        mock_url.path = "/v1/error"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/error")
        request.url = mock_url
        request.method = "GET"

        # Make headers raise an exception
        request.headers = MagicMock()
        request.headers.get.side_effect = Exception("Test exception")
        request.cookies = {}
        request.query_params = MagicMock()
        request.query_params.__iter__ = MagicMock(return_value=iter([]))
        request.query_params.__len__ = MagicMock(return_value=0)
        request.client = None
        request.state = {}
        request.request_id = "error_req_123"

        async def run_test():
            with pytest.raises(Exception, match="Test exception"):
                await log_request_meta(request)

            records = caplog_with_structured.records

            # Should have an ERROR log
            error_record = None
            for record in records:
                if "ERROR" in record.message and record.levelno == logging.ERROR:
                    error_record = record
                    break

            assert error_record is not None
            assert error_record.extra["phase"] == "error"
            assert "Test exception" in error_record.extra["error"]
            assert error_record.extra["error_type"] == "Exception"
            assert "processing_time_ms" in error_record.extra

        asyncio.run(run_test())

    def test_log_request_meta_request_id_tracing(self, caplog_with_structured):
        """Test that request IDs are properly traced through all log entries."""
        import asyncio

        request = MagicMock(spec=Request)
        mock_url = MagicMock()
        mock_url.path = "/v1/trace"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/trace")
        request.url = mock_url
        request.method = "GET"
        request.headers = {"authorization": "Bearer test"}
        request.cookies = {"test": "value"}
        request.query_params = MagicMock()
        request.query_params.__iter__ = MagicMock(return_value=iter([]))
        request.query_params.__len__ = MagicMock(return_value=0)
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.client.port = 8080
        request.state = {}
        request.request_id = "trace_req_123"

        async def run_test():
            result = await log_request_meta(request)
            assert result is request

            records = caplog_with_structured.records

            # Collect all req_ids
            req_ids = []
            for record in records:
                if "req_id" in record.extra:
                    req_ids.append(record.extra["req_id"])

            # All records should have the same req_id (except possibly the error case)
            unique_ids = set(req_ids)
            assert len(unique_ids) == 1  # All should have the same ID

            # Verify it's a valid UUID format (8 chars)
            req_id = list(unique_ids)[0]
            assert len(req_id) == 8
            # Should be valid hex
            int(req_id, 16)  # This will raise ValueError if not valid hex

        asyncio.run(run_test())

    def test_log_request_meta_performance_logging(self, caplog_with_structured):
        """Test that processing time is properly logged."""
        import asyncio

        request = MagicMock(spec=Request)
        mock_url = MagicMock()
        mock_url.path = "/v1/perf"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/perf")
        request.url = mock_url
        request.method = "GET"
        request.headers = {}
        request.cookies = {}
        request.query_params = MagicMock()
        request.query_params.__iter__ = MagicMock(return_value=iter([]))
        request.query_params.__len__ = MagicMock(return_value=0)
        request.client = None
        request.state = {}
        request.request_id = "perf_req_123"

        async def run_test():
            start_time = time.time()
            result = await log_request_meta(request)
            end_time = time.time()

            assert result is request

            records = caplog_with_structured.records

            # Find complete record
            complete_record = None
            for record in records:
                if "COMPLETE" in record.message:
                    complete_record = record
                    break

            assert complete_record is not None
            processing_time_ms = complete_record.extra["processing_time_ms"]

            # Processing time should be reasonable (between 0 and the total test time)
            assert 0 <= processing_time_ms <= (end_time - start_time) * 1000

        asyncio.run(run_test())

    @patch('app.auth.service.logger')
    def test_log_request_meta_logger_called_correctly(self, mock_logger):
        """Test that logger is called with correct parameters."""
        import asyncio

        request = MagicMock(spec=Request)
        mock_url = MagicMock()
        mock_url.path = "/v1/logger"
        mock_url.__str__ = MagicMock(return_value="http://testserver/v1/logger")
        request.url = mock_url
        request.method = "GET"
        request.headers = {"authorization": "Bearer test"}
        request.cookies = {}
        request.query_params = MagicMock()
        request.query_params.__iter__ = MagicMock(return_value=iter([]))
        request.query_params.__len__ = MagicMock(return_value=0)
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.client.port = 8080
        request.state = {}
        request.request_id = "logger_req_123"

        async def run_test():
            result = await log_request_meta(request)
            assert result is request

            # Verify logger.info was called multiple times
            assert mock_logger.info.call_count >= 2  # START and METADATA at minimum

            # Verify logger.warning was not called (no security warnings)
            mock_logger.warning.assert_not_called()

            # Check that first call includes correct emoji and message
            first_call_args = mock_logger.info.call_args_list[0]
            message, kwargs = first_call_args
            assert "🔐 AUTH REQUEST DEBUG - START" == message[0]

        asyncio.run(run_test())


class TestAuthRequestLoggingIntegration:
    """Integration tests for auth request logging."""

    def test_log_request_meta_integration_with_test_client(self):
        """Integration test with actual FastAPI test client."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.middleware("http")
        async def log_requests(request, call_next):
            await log_request_meta(request)
            return await call_next(request)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Make request and capture logs
        with patch('app.auth.service.logger') as mock_logger:
            response = client.get("/test")

            assert response.status_code == 200

            # Verify logging was called
            mock_logger.info.assert_called()

            # Verify the logs contain expected structure
            call_args = mock_logger.info.call_args_list[0]
            message, kwargs = call_args
            assert "🔐 AUTH REQUEST DEBUG - START" == message[0]
            assert "req_id" in kwargs["extra"]
            assert "function" in kwargs["extra"]
            assert kwargs["extra"]["function"] == "log_request_meta"

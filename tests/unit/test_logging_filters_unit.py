import logging
import pytest
from app.logging_config import (
    CORSConfigFilter,
    VectorStoreWarningFilter,
    OllamaHealthFilter,
    CookieTTLFilter,
    SecretCheckFilter,
    HealthCheckFilter
)


class TestCORSConfigFilter:
    def test_cors_config_filter_mutes_in_info_mode(self):
        filter_obj = CORSConfigFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="CORS CONFIGURATION DEBUG",
            args=(),
            exc_info=None
        )
        assert not filter_obj.filter(record)

    def test_cors_config_filter_allows_in_debug_mode(self):
        filter_obj = CORSConfigFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="CORS CONFIGURATION DEBUG",
            args=(),
            exc_info=None
        )
        assert filter_obj.filter(record)

    def test_cors_config_filter_allows_other_messages(self):
        filter_obj = CORSConfigFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Normal log message",
            args=(),
            exc_info=None
        )
        assert filter_obj.filter(record)


class TestVectorStoreWarningFilter:
    def test_vector_store_warning_filter_shows_once(self):
        filter_obj = VectorStoreWarningFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Vector store warning message",
            args=(),
            exc_info=None
        )
        # First occurrence should be shown
        assert filter_obj.filter(record)
        # Second occurrence should be muted
        assert not filter_obj.filter(record)

    def test_vector_store_warning_filter_allows_other_warnings(self):
        filter_obj = VectorStoreWarningFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Other warning message",
            args=(),
            exc_info=None
        )
        assert filter_obj.filter(record)

    def test_vector_store_warning_filter_allows_info_level(self):
        filter_obj = VectorStoreWarningFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Vector store info message",
            args=(),
            exc_info=None
        )
        assert filter_obj.filter(record)


class TestOllamaHealthFilter:
    def test_ollama_health_filter_mutes_health_checks(self):
        filter_obj = OllamaHealthFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Ollama health check successful",
            args=(),
            exc_info=None
        )
        assert not filter_obj.filter(record)

    def test_ollama_health_filter_allows_other_messages(self):
        filter_obj = OllamaHealthFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Normal log message",
            args=(),
            exc_info=None
        )
        assert filter_obj.filter(record)

    def test_ollama_health_filter_allows_error_level(self):
        filter_obj = OllamaHealthFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Ollama health check failed",
            args=(),
            exc_info=None
        )
        assert filter_obj.filter(record)


class TestCookieTTLFilter:
    def test_cookie_ttl_filter_simplifies_ttl_messages(self):
        filter_obj = CookieTTLFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Cookie TTL: ttl=3600",
            args=(),
            exc_info=None
        )
        filter_obj.filter(record)
        assert "Cookie TTL: enabled" in record.msg

    def test_cookie_ttl_filter_removes_emojis(self):
        filter_obj = CookieTTLFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="🔍 Debug message with emoji",
            args=(),
            exc_info=None
        )
        filter_obj.filter(record)
        assert "Debug message with emoji" in record.msg
        assert "🔍" not in record.msg


class TestSecretCheckFilter:
    def test_secret_check_filter_condenses_repeated_checks(self):
        filter_obj = SecretCheckFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="SECRET USAGE VERIFICATION ON BOOT",
            args=(),
            exc_info=None
        )
        # First occurrence should be shown
        assert filter_obj.filter(record)
        # Second occurrence should be muted
        assert not filter_obj.filter(record)

    def test_secret_check_filter_allows_different_messages(self):
        filter_obj = SecretCheckFilter()
        record1 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="SECRET USAGE VERIFICATION ON BOOT",
            args=(),
            exc_info=None
        )
        record2 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Different secret message",
            args=(),
            exc_info=None
        )
        # Both should be shown as they're different
        assert filter_obj.filter(record1)
        assert filter_obj.filter(record2)


class TestHealthCheckFilter:
    def test_health_check_filter_mutes_health_paths(self):
        filter_obj = HealthCheckFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Request to /healthz",
            args=(),
            exc_info=None
        )
        # Set the path attribute that the filter checks
        record.path = "/healthz"
        assert not filter_obj.filter(record)

    def test_health_check_filter_allows_other_paths(self):
        filter_obj = HealthCheckFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Request to /api/v1/users",
            args=(),
            exc_info=None
        )
        record.path = "/api/v1/users"
        assert filter_obj.filter(record)

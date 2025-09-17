"""
Test CI/environment hardening to ensure tests don't reach out to external services.
"""

import os


def test_env_hardening_external_services_disabled():
    """Verify that external service integrations are disabled in test environment."""

    # Core environment hardening variables
    assert os.getenv("ENV") == "test", "ENV should be set to 'test'"
    assert os.getenv("DEV_MODE") == "1", "DEV_MODE should be enabled for tests"
    assert os.getenv("ASGI_AUTO_APP") == "0", "ASGI_AUTO_APP should be disabled"

    # Telemetry and monitoring disabled
    assert os.getenv("OTEL_ENABLED") == "0", "OpenTelemetry should be disabled"
    assert os.getenv("PROMETHEUS_ENABLED") == "0", "Prometheus should be disabled"

    # Vector store relaxed
    assert os.getenv("STRICT_VECTOR_STORE") == "0", "Vector store should not be strict"

    # External API keys empty/disabled
    openai_key = os.getenv("OPENAI_API_KEY", "")
    assert openai_key == "", f"OPENAI_API_KEY should be empty, got: '{openai_key}'"

    # External service integrations disabled
    assert os.getenv("LLAMA_ENABLED") == "0", "LLaMA should be disabled"
    assert (
        os.getenv("HOME_ASSISTANT_ENABLED") == "0"
    ), "Home Assistant should be disabled"

    # Additional hardening flags
    assert os.getenv("DISABLE_EXTERNAL_APIS") == "1", "External APIs should be disabled"
    assert os.getenv("TEST_MODE") == "1", "TEST_MODE should be enabled"
    assert (
        os.getenv("DISABLE_NETWORK_REQUESTS") == "1"
    ), "Network requests should be disabled"
    assert os.getenv("DISABLE_EMAIL_SENDING") == "1", "Email sending should be disabled"
    assert os.getenv("DISABLE_WEBHOOKS") == "1", "Webhooks should be disabled"


def test_env_hardening_no_external_dependencies():
    """Verify that external service integrations are properly disabled."""

    # Check that critical external services are disabled
    # These should definitely be disabled to prevent external API calls during tests

    disabled_services = [
        "LLAMA_ENABLED",
        "HOME_ASSISTANT_ENABLED",
        "OTEL_ENABLED",
        "PROMETHEUS_ENABLED",
    ]

    for service in disabled_services:
        value = os.getenv(service, "")
        assert value in [
            "0",
            "",
            "false",
            "False",
        ], f"{service} should be disabled (0/false/empty), got: '{value}'"

    # Database URL should be test database
    db_url = os.getenv("DATABASE_URL", "")
    assert (
        "test" in db_url.lower()
    ), f"DATABASE_URL should contain 'test', got: {db_url}"

    # OPENAI_API_KEY should be empty or a test key (not a real production key)
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        # If it's set, it should be a test/dummy key, not a real production key
        assert not openai_key.startswith(
            "sk-"
        ), f"OPENAI_API_KEY appears to be a real production key: {openai_key[:20]}..."
        assert openai_key in [
            "",
            "test_key",
            "dummy_key",
        ], f"OPENAI_API_KEY should be empty or test key, got: '{openai_key}'"


def test_env_hardening_isolation():
    """Verify test environment is properly isolated from production."""

    # Test that we're in a test environment
    assert os.getenv("PYTEST_RUNNING") == "1", "PYTEST_RUNNING should be set"

    # Test that production features are disabled
    assert (
        os.getenv("RATE_LIMIT_MODE") == "off"
    ), "Rate limiting should be disabled in tests"

    # Test that dev features are configured appropriately
    assert os.getenv("DEV_MODE") == "1", "DEV_MODE should be enabled for tests"
    assert (
        os.getenv("AUTH_DEV_BYPASS") == "0"
    ), "AUTH_DEV_BYPASS should be disabled for proper security testing"

import pytest


@pytest.mark.asyncio
async def test_openai_startup_ping_gated(monkeypatch):
    """Test that OpenAI startup pings are properly gated."""
    from app.startup import check_vendor_health_gated

    # Ensure gating is disabled by default
    monkeypatch.delenv("STARTUP_VENDOR_PINGS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Should return skipped status when gated off
    result = await check_vendor_health_gated("openai")
    assert result["status"] == "skipped"
    assert result["reason"] == "pings_disabled"


@pytest.mark.asyncio
async def test_openai_startup_ping_enabled_missing_key(monkeypatch):
    """Test OpenAI startup ping when enabled but missing API key."""
    from app.startup import check_vendor_health_gated

    # Enable pings but don't set API key
    monkeypatch.setenv("STARTUP_VENDOR_PINGS", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Should return missing config status
    result = await check_vendor_health_gated("openai")
    assert result["status"] == "missing_config"
    assert result["config"] == "OPENAI_API_KEY"


@pytest.mark.asyncio
async def test_unknown_vendor(monkeypatch):
    """Test handling of unknown vendor."""
    from app.startup import check_vendor_health_gated

    # Enable pings
    monkeypatch.setenv("STARTUP_VENDOR_PINGS", "1")

    # Test with unknown vendor
    result = await check_vendor_health_gated("unknown_vendor")
    assert result["status"] == "unknown_vendor"
    assert result["vendor"] == "unknown_vendor"

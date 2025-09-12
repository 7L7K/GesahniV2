
import pytest


@pytest.mark.asyncio
async def test_lifespan_profile_ci(monkeypatch):
    """Ensure startup profile selects the CI profile when CI=1."""
    monkeypatch.setenv("CI", "1")
    # Import lazily to ensure monkeypatch applied
    from app.startup.config import detect_profile

    prof = detect_profile()
    assert prof.name == "ci"
    assert "init_home_assistant" not in prof.components
    assert "init_llama" not in prof.components


@pytest.mark.asyncio
async def test_util_check_vendor_gating(monkeypatch):
    """Vendor checks are gated by STARTUP_VENDOR_PINGS flag."""
    monkeypatch.delenv("STARTUP_VENDOR_PINGS", raising=False)
    from app.startup.vendor import check_vendor_health_gated

    res = await check_vendor_health_gated("openai")
    assert res["status"] == "skipped"

    monkeypatch.setenv("STARTUP_VENDOR_PINGS", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res2 = await check_vendor_health_gated("openai")
    assert res2["status"] == "missing_config"



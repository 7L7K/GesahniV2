"""
Integration tests for config guard in actual startup scenarios.
"""
import pytest
import asyncio
from unittest.mock import patch

from app.main import create_app
from app.startup import lifespan


class TestConfigGuardStartup:
    """Test that config guard prevents startup with invalid prod config."""

    @pytest.mark.asyncio
    async def test_weak_jwt_prevents_startup_in_prod(self):
        """Test that weak JWT secret prevents app startup in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "weak",  # Too short
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            app = create_app()
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass  # Should not reach here

            # Should contain our ConfigError message
            assert "JWT_SECRET too weak" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_insecure_cookies_prevent_startup_in_prod(self):
        """Test that insecure cookies prevent app startup in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "0",  # Insecure
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            app = create_app()
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass

            assert "COOKIES_SECURE must be enabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_weak_samesite_prevents_startup_in_prod(self):
        """Test that weak SameSite prevents app startup in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "lax",  # Not strict
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            app = create_app()
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass

            assert "COOKIES_SAMESITE must be 'strict'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disabled_request_ids_prevent_startup_in_prod(self):
        """Test that disabled request IDs prevent app startup in prod."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "0"  # Disabled
        }, clear=True):
            app = create_app()
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass

            assert "REQ_ID_ENABLED must be on" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_valid_prod_config_allows_startup(self):
        """Test that valid prod config allows app startup."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "JWT_SECRET": "a" * 32,
            "COOKIES_SECURE": "1",
            "COOKIES_SAMESITE": "strict",
            "REQ_ID_ENABLED": "1"
        }, clear=True):
            app = create_app()
            # Should complete successfully
            async with lifespan(app):
                pass

    @pytest.mark.asyncio
    async def test_dev_mode_allows_weak_config(self):
        """Test that dev mode allows weak config (guardrails skipped)."""
        with patch.dict("os.environ", {
            "ENV": "prod",
            "DEV_MODE": "1",  # Dev mode enabled
            "JWT_SECRET": "weak",  # Would be rejected without dev mode
            "COOKIES_SECURE": "0",  # Would be rejected without dev mode
            "COOKIES_SAMESITE": "lax",  # Would be rejected without dev mode
            "REQ_ID_ENABLED": "0"  # Would be rejected without dev mode
        }, clear=True):
            app = create_app()
            # Should complete successfully (dev mode bypasses guards)
            async with lifespan(app):
                pass

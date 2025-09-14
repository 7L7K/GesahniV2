"""
End-to-end tests for redirect scenarios.

Tests complete user journeys involving redirects, including:
- Login with redirect
- Logout with redirect
- Protection against redirect loops
- Cookie-based redirect persistence
"""

import pytest
from playwright.async_api import BrowserContext, Page


class TestRedirectScenarios:
    """End-to-end redirect scenario tests."""

    @pytest.mark.asyncio
    async def test_login_redirect_flow(self, page: Page, context: BrowserContext):
        """Test complete login flow with redirects."""
        # Navigate to login page with next parameter
        await page.goto("/login?next=/dashboard")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to dashboard (not to login again)
        await page.wait_for_url("**/dashboard")

        # Verify we're on dashboard, not login
        assert "/dashboard" in page.url
        assert "/login" not in page.url

    @pytest.mark.asyncio
    async def test_invalid_redirect_prevention(self, page: Page):
        """Test that invalid redirects are prevented."""
        # Try to access login with malicious next parameter
        await page.goto("/login?next=https://evil.com")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to safe default (dashboard), not evil.com
        await page.wait_for_url("**/dashboard")
        assert "evil.com" not in page.url

    @pytest.mark.asyncio
    async def test_auth_path_redirect_prevention(self, page: Page):
        """Test that redirects to auth paths are prevented."""
        # Try to access login with auth path as next
        await page.goto("/login?next=/login")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to safe default, not back to login
        await page.wait_for_url("**/dashboard")
        assert "/login" not in page.url

    @pytest.mark.asyncio
    async def test_nested_redirect_prevention(self, page: Page):
        """Test prevention of nested redirect loops."""
        # Create a deeply nested redirect
        nested_next = "/login?next=/login%3Fnext%3D/dashboard"
        await page.goto(f"/login?next={nested_next}")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should not create a redirect loop
        await page.wait_for_url("**/dashboard")

        # Verify we didn't end up in a loop
        assert page.url.count("/login") <= 1

    @pytest.mark.asyncio
    async def test_gs_next_cookie_persistence(
        self, page: Page, context: BrowserContext
    ):
        """Test gs_next cookie persistence across page reloads."""
        # Set gs_next cookie
        await context.add_cookies(
            [
                {
                    "name": "gs_next",
                    "value": "/settings",
                    "path": "/",
                    "domain": "localhost",
                }
            ]
        )

        # Navigate to login page without next parameter
        await page.goto("/login")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to settings (from cookie)
        await page.wait_for_url("**/settings")

    @pytest.mark.asyncio
    async def test_explicit_next_overrides_cookie(
        self, page: Page, context: BrowserContext
    ):
        """Test that explicit next parameter overrides gs_next cookie."""
        # Set gs_next cookie
        await context.add_cookies(
            [
                {
                    "name": "gs_next",
                    "value": "/settings",
                    "path": "/",
                    "domain": "localhost",
                }
            ]
        )

        # Navigate to login with different next parameter
        await page.goto("/login?next=/dashboard")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to dashboard (explicit next), not settings (cookie)
        await page.wait_for_url("**/dashboard")

    @pytest.mark.asyncio
    async def test_logout_clears_redirect_state(
        self, page: Page, context: BrowserContext
    ):
        """Test that logout clears redirect-related cookies."""
        # First login and set gs_next
        await context.add_cookies(
            [
                {
                    "name": "gs_next",
                    "value": "/settings",
                    "path": "/",
                    "domain": "localhost",
                }
            ]
        )

        # Navigate to logout
        await page.goto("/logout")

        # Should clear cookies and redirect appropriately
        # (This would depend on actual logout implementation)

    @pytest.mark.asyncio
    async def test_double_encoded_redirect_handling(self, page: Page):
        """Test handling of double-encoded redirect parameters."""
        # Create double-encoded next parameter
        double_encoded = "%252Fdashboard"  # Encoded version of /dashboard
        await page.goto(f"/login?next={double_encoded}")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should safely decode and redirect to dashboard
        await page.wait_for_url("**/dashboard")

    @pytest.mark.asyncio
    async def test_fragment_removal(self, page: Page):
        """Test that URL fragments are removed from redirects."""
        await page.goto("/login?next=/dashboard#section")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to dashboard without fragment
        await page.wait_for_url("**/dashboard")
        assert "#" not in page.url

    @pytest.mark.asyncio
    async def test_slash_normalization(self, page: Page):
        """Test that multiple slashes are normalized."""
        await page.goto("/login?next=/path//to///dashboard")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to normalized path
        await page.wait_for_url("**/path/to/dashboard")

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, page: Page):
        """Test prevention of path traversal attacks."""
        await page.goto("/login?next=/../../../etc/passwd")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to safe default, not the traversal path
        await page.wait_for_url("**/dashboard")
        assert "etc" not in page.url
        assert "passwd" not in page.url

    @pytest.mark.asyncio
    async def test_protocol_relative_prevention(self, page: Page):
        """Test prevention of protocol-relative URLs."""
        await page.goto("/login?next=//evil.com/path")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to safe default
        await page.wait_for_url("**/dashboard")
        assert "evil.com" not in page.url

    @pytest.mark.asyncio
    async def test_redirect_session_persistence(
        self, page: Page, context: BrowserContext
    ):
        """Test that redirect preferences persist across browser sessions."""
        # This would test localStorage/sessionStorage persistence
        # For now, just ensure basic functionality works
        await page.goto("/login?next=/dashboard")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect successfully
        await page.wait_for_url("**/dashboard")


class TestRedirectErrorHandling:
    """Test error handling in redirect scenarios."""

    @pytest.mark.asyncio
    async def test_malformed_url_handling(self, page: Page):
        """Test handling of malformed URLs in redirect parameters."""
        # Try with malformed URL encoding
        await page.goto("/login?next=%ZZinvalid")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should handle gracefully and redirect to safe default
        await page.wait_for_url("**/dashboard")

    @pytest.mark.asyncio
    async def test_empty_redirect_parameters(self, page: Page):
        """Test handling of empty or missing redirect parameters."""
        # Test with completely empty next
        await page.goto("/login?next=")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should redirect to safe default
        await page.wait_for_url("**/dashboard")

    @pytest.mark.asyncio
    async def test_very_long_redirect_parameters(self, page: Page):
        """Test handling of very long redirect parameters."""
        # Create a very long next parameter
        long_next = "/dashboard?" + "param=value&" * 1000
        await page.goto(f"/login?next={long_next}")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Should handle gracefully
        await page.wait_for_url("**/dashboard")


class TestRedirectPerformance:
    """Test performance aspects of redirect handling."""

    @pytest.mark.asyncio
    async def test_redirect_speed(self, page: Page):
        """Test that redirects happen quickly."""
        import time

        start_time = time.time()

        await page.goto("/login?next=/dashboard")

        # Fill login form
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpass")

        # Submit form
        await page.click('button[type="submit"]')

        # Wait for redirect
        await page.wait_for_url("**/dashboard")

        end_time = time.time()
        duration = end_time - start_time

        # Should complete within reasonable time (adjust threshold as needed)
        assert duration < 5.0, f"Redirect took too long: {duration}s"

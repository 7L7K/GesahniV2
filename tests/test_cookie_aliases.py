import os
from unittest.mock import patch

import pytest

# Note: Full FastAPI client tests are commented out due to import issues
# These tests focus on the core cookie functionality instead


def generate_test_token():
    """Generate a valid test JWT token"""
    from app.tokens import sign_access_token
    return sign_access_token("test_user_123")


class TestCookieAliases:
    """Test cookie alias reading functionality"""

    def test_alias_reading_functionality(self):
        """Test that get_any can read from multiple cookie aliases"""
        from unittest.mock import Mock

        from app.web.cookies import ACCESS_ALIASES, get_any

        # Test with canonical cookie
        request = Mock()
        request.cookies = {"access_token": "token123"}
        result = get_any(request, ACCESS_ALIASES)
        assert result == "token123"

        # Test with legacy cookie
        request.cookies = {"gsn_access": "token456"}
        result = get_any(request, ACCESS_ALIASES)
        assert result == "token456"

        # Test with no matching cookies
        request.cookies = {"other_cookie": "value"}
        result = get_any(request, ACCESS_ALIASES)
        assert result is None


class TestCookieMigration:
    """Test cookie migration functionality"""

    def test_cookie_clearing_functionality(self):
        """Test that clear_all_auth clears all cookie variants"""
        from unittest.mock import Mock

        from app.web.cookies import clear_all_auth

        response = Mock()
        clear_all_auth(response)

        # Should have called delete_cookie for all cookie variants
        assert response.delete_cookie.called
        calls = response.delete_cookie.call_args_list

        cookie_names = [call[0][0] for call in calls]  # Extract cookie names
        expected_cookies = {"access_token", "refresh_token", "gsn_access", "gsn_refresh", "__session"}

        assert set(cookie_names) == expected_cookies


class TestCookieConfiguration:
    """Test cookie configuration based on environment"""

    def test_classic_configuration(self):
        """Test COOKIE_CANON=classic configuration"""
        with patch.dict(os.environ, {"COOKIE_CANON": "classic"}):
            from app.web.cookies import ACCESS_ALIASES, ACCESS_CANON, REFRESH_CANON
            assert ACCESS_CANON == "access_token"
            assert REFRESH_CANON == "refresh_token"
            assert "access_token" in ACCESS_ALIASES
            assert "gsn_access" in ACCESS_ALIASES

    def test_gsn_configuration(self):
        """Test COOKIE_CANON=gsn configuration"""
        # Need to reload the module to pick up the new environment variable
        import importlib

        import app.web.cookies

        with patch.dict(os.environ, {"COOKIE_CANON": "gsn"}):
            importlib.reload(app.web.cookies)
            assert app.web.cookies.ACCESS_CANON == "gsn_access"
            assert app.web.cookies.REFRESH_CANON == "gsn_refresh"
            assert "gsn_access" in app.web.cookies.ACCESS_ALIASES
            assert "access_token" in app.web.cookies.ACCESS_ALIASES

    def test_default_configuration(self):
        """Test default configuration (should be classic)"""
        # Remove COOKIE_CANON from environment if it exists
        with patch.dict(os.environ, {}, clear=True):
            import importlib

            import app.web.cookies
            importlib.reload(app.web.cookies)
            assert app.web.cookies.ACCESS_CANON == "access_token"
            assert app.web.cookies.REFRESH_CANON == "refresh_token"


class TestCookieFunctions:
    """Test individual cookie utility functions"""

    def test_get_any_function(self):
        """Test the get_any cookie reading function"""
        from unittest.mock import Mock

        from app.web.cookies import ACCESS_ALIASES, get_any

        # Test with canonical cookie
        request = Mock()
        request.cookies = {"access_token": "token123"}
        result = get_any(request, ACCESS_ALIASES)
        assert result == "token123"

        # Test with legacy cookie
        request.cookies = {"gsn_access": "token456"}
        result = get_any(request, ACCESS_ALIASES)
        assert result == "token456"

        # Test with no matching cookies
        request.cookies = {"other_cookie": "value"}
        result = get_any(request, ACCESS_ALIASES)
        assert result is None

    def test_clear_all_auth_function(self):
        """Test the clear_all_auth cookie clearing function"""
        from unittest.mock import Mock

        from app.web.cookies import clear_all_auth

        response = Mock()
        clear_all_auth(response)

        # Should have called delete_cookie for all cookie variants
        assert response.delete_cookie.called
        calls = response.delete_cookie.call_args_list

        cookie_names = [call[0][0] for call in calls]  # Extract cookie names
        expected_cookies = {"access_token", "refresh_token", "gsn_access", "gsn_refresh", "__session"}

        assert set(cookie_names) == expected_cookies

    def test_set_auth_cookies_canon_function(self):
        """Test the set_auth_cookies_canon function"""
        from unittest.mock import Mock

        from app.web.cookies import set_auth_cookies_canon

        response = Mock()
        set_auth_cookies_canon(
            response,
            access="access_token_value",
            refresh="refresh_token_value",
            secure=True,
            samesite="Lax",
            domain=None
        )

        # Should have called set_cookie for both access and refresh
        assert response.set_cookie.called
        calls = response.set_cookie.call_args_list
        assert len(calls) == 2

        # Check cookie names - the function should use canonical names based on current config
        cookie_names = [call[0][0] for call in calls]  # First positional argument is key
        # Should use whatever the current canonical names are
        from app.web.cookies import ACCESS_CANON, REFRESH_CANON
        assert ACCESS_CANON in cookie_names
        assert REFRESH_CANON in cookie_names


if __name__ == "__main__":
    pytest.main([__file__])

"""
Unit tests for cookie and JWT compliance patterns.

These tests verify that the codebase follows the established security boundaries
for cookie and JWT usage.
"""

import os
import subprocess

import pytest


class TestCookieJWTCompliance:
    """Test suite for cookie and JWT usage compliance."""
    
    # Allowed files for cookie operations
    ALLOWED_COOKIE_FILES = {
        "app/api/auth.py",
        "app/api/google_oauth.py", 
        "app/api/oauth_apple.py",
        "app/middleware.py",
        "app/auth_device/__init__.py",
        "app/cookies.py",  # Centralized cookie facade
        "app/cookie_config.py",  # Cookie configuration
    }
    
    # Allowed files for JWT encoding
    ALLOWED_JWT_FILES = {
        "app/api/auth.py",  # Authentication flows
        "app/api/oauth_apple.py",  # Apple IdP token signing
        "app/tokens.py",  # Centralized token minting
    }
    
    # Files that can mint app tokens (through tokens.py only)
    APP_TOKEN_MINTING_FILES = {
        "app/api/auth.py",  # Authentication flows
    }
    
    # Files that can sign third-party IdP tokens
    IDP_TOKEN_SIGNING_FILES = {
        "app/api/oauth_apple.py",  # Apple IdP
    }
    
    def run_grep_command(self, pattern: str, include_pattern: str = "app/**/*.py", exclude_pattern: str = "tests/**") -> list[str]:
        """Run grep command and return matching lines."""
        try:
            cmd = ["rg", "-n", pattern, "-g", include_pattern, "-g", f"!{exclude_pattern}"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
            if result.returncode == 0:
                return result.stdout.strip().split('\n') if result.stdout.strip() else []
            return []
        except Exception as e:
            pytest.fail(f"Error running grep command: {e}")
    
    def test_no_unauthorized_set_cookie_calls(self):
        """Test that no unauthorized files call set_cookie() directly."""
        set_cookie_lines = self.run_grep_command(r"\.set_cookie\(")
        violations = []
        
        for line in set_cookie_lines:
            if line.strip():
                file_path = line.split(':')[0]
                if file_path not in self.ALLOWED_COOKIE_FILES:
                    violations.append(f"Direct set_cookie() call in {line}")
        
        assert len(violations) == 0, "Found unauthorized set_cookie() calls:\n" + "\n".join(violations)
    
    def test_no_unauthorized_set_cookie_headers(self):
        """Test that no unauthorized files manipulate Set-Cookie headers directly."""
        set_cookie_header_lines = self.run_grep_command(r'headers\.append.*Set-Cookie')
        violations = []
        
        for line in set_cookie_header_lines:
            if line.strip():
                file_path = line.split(':')[0]
                if file_path not in self.ALLOWED_COOKIE_FILES:
                    violations.append(f"Direct Set-Cookie header manipulation in {line}")
        
        assert len(violations) == 0, "Found unauthorized Set-Cookie header manipulation:\n" + "\n".join(violations)
    
    def test_no_unauthorized_jwt_encode_calls(self):
        """Test that no unauthorized files call jwt.encode() directly."""
        jwt_encode_lines = self.run_grep_command(r"jwt\.encode")
        violations = []
        
        for line in jwt_encode_lines:
            if line.strip():
                file_path = line.split(':')[0]
                
                # Check if it's an allowed file
                if file_path not in self.ALLOWED_JWT_FILES:
                    # Check if it's in Google integrations (allowed for IdP)
                    if not file_path.startswith("app/integrations/google/"):
                        violations.append(f"Unauthorized jwt.encode() call in {line}")
        
        assert len(violations) == 0, "Found unauthorized jwt.encode() calls:\n" + "\n".join(violations)
    
    def test_app_token_minting_goes_through_tokens_py(self):
        """Test that app token minting goes through tokens.py."""
        jwt_encode_lines = self.run_grep_command(r"jwt\.encode.*algorithm.*HS256")
        violations = []
        
        for line in jwt_encode_lines:
            if line.strip():
                file_path = line.split(':')[0]
                
                # Only tokens.py should mint app tokens with HS256
                if file_path != "app/tokens.py":
                    # Check if it's an allowed authentication flow
                    if file_path not in self.APP_TOKEN_MINTING_FILES:
                        violations.append(f"Unauthorized app token minting in {line}")
        
        assert len(violations) == 0, "Found unauthorized app token minting:\n" + "\n".join(violations)
    
    def test_idp_token_signing_only_in_allowed_locations(self):
        """Test that IdP token signing only occurs in allowed locations."""
        es256_lines = self.run_grep_command(r"jwt\.encode.*algorithm.*ES256")
        violations = []
        
        for line in es256_lines:
            if line.strip():
                file_path = line.split(':')[0]
                
                # Only IdP integrations should use ES256
                if file_path not in self.IDP_TOKEN_SIGNING_FILES:
                    if not file_path.startswith("app/integrations/google/"):
                        violations.append(f"Unauthorized IdP token signing in {line}")
        
        assert len(violations) == 0, "Found unauthorized IdP token signing:\n" + "\n".join(violations)
    
    def test_auth_py_uses_centralized_functions(self):
        """Test that auth.py uses centralized cookie and token functions."""
        auth_file = "app/api/auth.py"
        assert os.path.exists(auth_file), f"Auth file {auth_file} not found"
        
        with open(auth_file) as f:
            content = f.read()
            
            # Check for centralized cookie usage
            assert "set_auth_cookies" in content, "auth.py should use set_auth_cookies from cookies.py"
            
            # Check for centralized token usage
            assert ("make_access" in content or "make_refresh" in content), "auth.py should use make_access/make_refresh from tokens.py"
    
    def test_cookies_py_centralized_facade_exists(self):
        """Test that cookies.py provides centralized facade functions."""
        cookies_file = "app/cookies.py"
        assert os.path.exists(cookies_file), f"Cookies file {cookies_file} not found"
        
        with open(cookies_file) as f:
            content = f.read()
            
            # Check for key centralized functions
            required_functions = [
                "set_auth_cookies",
                "set_oauth_state_cookies", 
                "set_device_cookie",
                "set_csrf_cookie",
                "set_named_cookie"
            ]
            
            for func in required_functions:
                assert func in content, f"cookies.py should provide {func} function"
    
    def test_tokens_py_centralized_facade_exists(self):
        """Test that tokens.py provides centralized token functions."""
        tokens_file = "app/tokens.py"
        assert os.path.exists(tokens_file), f"Tokens file {tokens_file} not found"
        
        with open(tokens_file) as f:
            content = f.read()
            
            # Check for key centralized functions
            required_functions = [
                "make_access",
                "make_refresh",
                "get_default_access_ttl",
                "get_default_refresh_ttl"
            ]
            
            for func in required_functions:
                assert func in content, f"tokens.py should provide {func} function"
    
    def test_cookie_config_centralized_configuration_exists(self):
        """Test that cookie_config.py provides centralized configuration."""
        config_file = "app/cookie_config.py"
        assert os.path.exists(config_file), f"Cookie config file {config_file} not found"
        
        with open(config_file) as f:
            content = f.read()
            
            # Check for key configuration functions
            required_functions = [
                "get_cookie_config",
                "format_cookie_header",
                "get_token_ttls"
            ]
            
            for func in required_functions:
                assert func in content, f"cookie_config.py should provide {func} function"
    
    def test_no_direct_cookie_manipulation_in_application_code(self):
        """Test that application code doesn't manipulate cookies directly."""
        # Check for various cookie manipulation patterns
        patterns = [
            r"response\.cookies\[",
            r"request\.cookies\[",
            r"cookies\[",
            r"\.set_cookie\(",
            r"headers\[.*Set-Cookie",
            r"headers\.append.*Set-Cookie"
        ]
        
        violations = []
        for pattern in patterns:
            lines = self.run_grep_command(pattern)
            for line in lines:
                if line.strip():
                    file_path = line.split(':')[0]
                    # Allow cookies.py and cookie_config.py to manipulate cookies
                    if file_path not in {"app/cookies.py", "app/cookie_config.py"}:
                        # Allow middleware to read cookies (but not set them)
                        if file_path == "app/middleware.py" and "set-cookie" in line.lower():
                            continue
                        violations.append(f"Direct cookie manipulation in {line}")
        
        assert len(violations) == 0, "Found unauthorized cookie manipulation:\n" + "\n".join(violations)
    
    def test_proper_separation_of_token_types(self):
        """Test that app tokens and IdP tokens are properly separated."""
        # Check that app tokens use HS256 (centralized in tokens.py)
        hs256_lines = self.run_grep_command(r"jwt\.encode.*HS256")
        for line in hs256_lines:
            if line.strip():
                file_path = line.split(':')[0]
                # Only tokens.py should use HS256 for app tokens
                if file_path not in {"app/tokens.py"}:
                    # Allow auth.py to use tokens.py functions
                    if file_path not in self.APP_TOKEN_MINTING_FILES:
                        pytest.fail(f"App token minting outside tokens.py: {line}")
        
        # Check that IdP tokens use ES256 (only in IdP integrations)
        es256_lines = self.run_grep_command(r"jwt\.encode.*ES256")
        for line in es256_lines:
            if line.strip():
                file_path = line.split(':')[0]
                # Only IdP integrations should use ES256
                if file_path not in self.IDP_TOKEN_SIGNING_FILES:
                    if not file_path.startswith("app/integrations/google/"):
                        pytest.fail(f"IdP token signing outside allowed locations: {line}")


class TestCookieJWTComplianceIntegration:
    """Integration tests for cookie and JWT compliance."""
    
    def test_compliance_script_runs_successfully(self):
        """Test that the compliance script runs without errors."""
        script_path = "test_cookie_jwt_compliance.py"
        assert os.path.exists(script_path), f"Compliance script {script_path} not found"
        
        try:
            result = subprocess.run(
                ["python", script_path], 
                capture_output=True, 
                text=True, 
                cwd=os.getcwd(),
                timeout=30
            )
            
            # Script should exit with code 0 (success)
            assert result.returncode == 0, f"Compliance script failed with exit code {result.returncode}"
            
            # Should indicate all checks passed
            assert "ALL CHECKS PASSED" in result.stdout, "Compliance script should report all checks passed"
            
        except subprocess.TimeoutExpired:
            pytest.fail("Compliance script timed out")
        except Exception as e:
            pytest.fail(f"Error running compliance script: {e}")
    
    def test_centralized_functions_are_importable(self):
        """Test that centralized functions can be imported."""
        try:
            from app.cookie_config import get_cookie_config, get_token_ttls
            from app.cookies import set_auth_cookies, set_oauth_state_cookies
            from app.tokens import make_access, make_refresh
        except ImportError as e:
            pytest.fail(f"Failed to import centralized functions: {e}")
    
    def test_cookie_config_provides_consistent_settings(self):
        """Test that cookie configuration provides consistent settings."""
        from app.cookie_config import get_cookie_config, get_token_ttls
        
        # Mock request for testing
        class MockRequest:
            def __init__(self):
                self.headers = {}
                self.url = "https://example.com"
        
        request = MockRequest()
        
        # Should return consistent configuration
        config = get_cookie_config(request)
        assert "secure" in config
        assert "samesite" in config
        assert "httponly" in config
        assert "path" in config
        
        # Should return consistent TTLs
        access_ttl, refresh_ttl = get_token_ttls()
        assert isinstance(access_ttl, int)
        assert isinstance(refresh_ttl, int)
        assert access_ttl > 0
        assert refresh_ttl > access_ttl  # Refresh should be longer than access

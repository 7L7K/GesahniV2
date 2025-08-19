"""Test the new environment configuration system."""

import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from app.env_utils import load_env


class TestEnvironmentConfiguration:
    """Test the multi-environment configuration system."""

    def setup_method(self):
        """Set up test environment."""
        # Store original environment
        self.original_env = os.environ.copy()
        
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        
        # Create test environment files
        self.create_test_env_files()

    def teardown_method(self):
        """Clean up test environment."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up temporary directory
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def create_test_env_files(self):
        """Create test environment files."""
        # Create env.dev
        with open("env.dev", "w") as f:
            f.write("""# Development environment
APP_URL=http://localhost:3000
API_URL=http://localhost:8000
CORS_ALLOW_ORIGINS=http://localhost:3000
COOKIE_SECURE=0
COOKIE_SAMESITE=lax
NEXT_PUBLIC_HEADER_AUTH_MODE=0
DEV_MODE=1
JWT_SECRET=dev-secret
""")

        # Create env.staging
        with open("env.staging", "w") as f:
            f.write("""# Staging environment
APP_URL=https://staging.gesahni.com
API_URL=https://api-staging.gesahni.com
CORS_ALLOW_ORIGINS=https://staging.gesahni.com
COOKIE_SECURE=1
COOKIE_SAMESITE=lax
NEXT_PUBLIC_HEADER_AUTH_MODE=0
DEV_MODE=0
JWT_SECRET=staging-secret
""")

        # Create env.prod
        with open("env.prod", "w") as f:
            f.write("""# Production environment
APP_URL=https://app.gesahni.com
API_URL=https://api.gesahni.com
CORS_ALLOW_ORIGINS=https://app.gesahni.com
COOKIE_SECURE=1
COOKIE_SAMESITE=strict
NEXT_PUBLIC_HEADER_AUTH_MODE=0
DEV_MODE=0
JWT_SECRET=prod-secret
""")

    def test_env_dev_loading(self):
        """Test loading development environment."""
        # Copy dev environment to .env
        shutil.copy("env.dev", ".env")
        
        # Load environment
        load_env(force=True)
        
        # Verify environment-specific variables
        assert os.environ["APP_URL"] == "http://localhost:3000"
        assert os.environ["API_URL"] == "http://localhost:8000"
        assert os.environ["CORS_ALLOW_ORIGINS"] == "http://localhost:3000"
        assert os.environ["COOKIE_SECURE"] == "0"
        assert os.environ["COOKIE_SAMESITE"] == "lax"
        assert os.environ["NEXT_PUBLIC_HEADER_AUTH_MODE"] == "0"
        assert os.environ["DEV_MODE"] == "1"
        assert os.environ["JWT_SECRET"] == "dev-secret"

    def test_env_staging_loading(self):
        """Test loading staging environment."""
        # Copy staging environment to .env
        shutil.copy("env.staging", ".env")
        
        # Load environment
        load_env(force=True)
        
        # Verify environment-specific variables
        assert os.environ["APP_URL"] == "https://staging.gesahni.com"
        assert os.environ["API_URL"] == "https://api-staging.gesahni.com"
        assert os.environ["CORS_ALLOW_ORIGINS"] == "https://staging.gesahni.com"
        assert os.environ["COOKIE_SECURE"] == "1"
        assert os.environ["COOKIE_SAMESITE"] == "lax"
        assert os.environ["NEXT_PUBLIC_HEADER_AUTH_MODE"] == "0"
        assert os.environ["DEV_MODE"] == "0"
        assert os.environ["JWT_SECRET"] == "staging-secret"

    def test_env_prod_loading(self):
        """Test loading production environment."""
        # Copy production environment to .env
        shutil.copy("env.prod", ".env")
        
        # Load environment
        load_env(force=True)
        
        # Verify environment-specific variables
        assert os.environ["APP_URL"] == "https://app.gesahni.com"
        assert os.environ["API_URL"] == "https://api.gesahni.com"
        assert os.environ["CORS_ALLOW_ORIGINS"] == "https://app.gesahni.com"
        assert os.environ["COOKIE_SECURE"] == "1"
        assert os.environ["COOKIE_SAMESITE"] == "strict"
        assert os.environ["NEXT_PUBLIC_HEADER_AUTH_MODE"] == "0"
        assert os.environ["DEV_MODE"] == "0"
        assert os.environ["JWT_SECRET"] == "prod-secret"

    def test_env_precedence(self):
        """Test that .env takes precedence over environment files."""
        # Create .env with some overrides
        with open(".env", "w") as f:
            f.write("""# Local overrides
APP_URL=http://custom.localhost:3000
JWT_SECRET=custom-secret
CUSTOM_VAR=local-value
""")
        
        # Load environment
        load_env(force=True)
        
        # Verify .env takes precedence
        assert os.environ["APP_URL"] == "http://custom.localhost:3000"
        assert os.environ["JWT_SECRET"] == "custom-secret"
        assert os.environ["CUSTOM_VAR"] == "local-value"
        
        # Verify other variables are filled from environment files
        assert "API_URL" in os.environ
        assert "CORS_ALLOW_ORIGINS" in os.environ

    def test_missing_env_files(self):
        """Test behavior when environment files are missing."""
        # Remove environment files
        for env_file in ["env.dev", "env.staging", "env.prod"]:
            if os.path.exists(env_file):
                os.remove(env_file)
        
        # Create minimal .env
        with open(".env", "w") as f:
            f.write("APP_URL=http://localhost:3000\n")
        
        # Load environment (should not fail)
        load_env(force=True)
        
        # Verify basic functionality still works
        assert os.environ["APP_URL"] == "http://localhost:3000"

    def test_environment_specific_security_settings(self):
        """Test that security settings are appropriate for each environment."""
        # Test development security (relaxed)
        shutil.copy("env.dev", ".env")
        load_env(force=True)
        assert os.environ["COOKIE_SECURE"] == "0"
        assert os.environ["COOKIE_SAMESITE"] == "lax"
        assert os.environ["DEV_MODE"] == "1"
        
        # Test staging security (production-like)
        shutil.copy("env.staging", ".env")
        load_env(force=True)
        assert os.environ["COOKIE_SECURE"] == "1"
        assert os.environ["COOKIE_SAMESITE"] == "lax"
        assert os.environ["DEV_MODE"] == "0"
        
        # Test production security (strict)
        shutil.copy("env.prod", ".env")
        load_env(force=True)
        assert os.environ["COOKIE_SECURE"] == "1"
        assert os.environ["COOKIE_SAMESITE"] == "strict"
        assert os.environ["DEV_MODE"] == "0"

    def test_url_configuration_per_environment(self):
        """Test that URLs are correctly configured for each environment."""
        # Development URLs
        shutil.copy("env.dev", ".env")
        load_env(force=True)
        assert os.environ["APP_URL"] == "http://localhost:3000"
        assert os.environ["API_URL"] == "http://localhost:8000"
        assert os.environ["CORS_ALLOW_ORIGINS"] == "http://localhost:3000"
        
        # Staging URLs
        shutil.copy("env.staging", ".env")
        load_env(force=True)
        assert os.environ["APP_URL"] == "https://staging.gesahni.com"
        assert os.environ["API_URL"] == "https://api-staging.gesahni.com"
        assert os.environ["CORS_ALLOW_ORIGINS"] == "https://staging.gesahni.com"
        
        # Production URLs
        shutil.copy("env.prod", ".env")
        load_env(force=True)
        assert os.environ["APP_URL"] == "https://app.gesahni.com"
        assert os.environ["API_URL"] == "https://api.gesahni.com"
        assert os.environ["CORS_ALLOW_ORIGINS"] == "https://app.gesahni.com"

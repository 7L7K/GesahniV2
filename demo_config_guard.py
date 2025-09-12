#!/usr/bin/env python3
"""
Demonstration of production configuration guardrails.
Run this script to see how the config guard validates configurations.
"""
import os

from app.startup.config_guard import ConfigError, assert_strict_prod


def demo_config_guard():
    """Demonstrate config guard functionality."""

    print("🔒 Production Configuration Guardrails Demo")
    print("=" * 50)

    # Test cases
    test_cases = [
        {
            "name": "Weak JWT Secret",
            "env": {
                "ENV": "prod",
                "JWT_SECRET": "weak",
                "COOKIES_SECURE": "1",
                "COOKIES_SAMESITE": "strict",
                "REQ_ID_ENABLED": "1"
            },
            "expected_error": "JWT_SECRET too weak"
        },
        {
            "name": "Insecure Cookies",
            "env": {
                "ENV": "prod",
                "JWT_SECRET": "a" * 32,
                "COOKIES_SECURE": "0",
                "COOKIES_SAMESITE": "strict",
                "REQ_ID_ENABLED": "1"
            },
            "expected_error": "COOKIES_SECURE must be enabled"
        },
        {
            "name": "Weak SameSite",
            "env": {
                "ENV": "prod",
                "JWT_SECRET": "a" * 32,
                "COOKIES_SECURE": "1",
                "COOKIES_SAMESITE": "lax",
                "REQ_ID_ENABLED": "1"
            },
            "expected_error": "COOKIES_SAMESITE must be 'strict'"
        },
        {
            "name": "Valid Prod Config",
            "env": {
                "ENV": "prod",
                "JWT_SECRET": "a" * 32,
                "COOKIES_SECURE": "1",
                "COOKIES_SAMESITE": "strict",
                "REQ_ID_ENABLED": "1"
            },
            "should_pass": True
        },
        {
            "name": "Dev Mode Bypass",
            "env": {
                "ENV": "prod",
                "DEV_MODE": "1",
                "JWT_SECRET": "weak",
                "COOKIES_SECURE": "0",
                "COOKIES_SAMESITE": "lax",
                "REQ_ID_ENABLED": "0"
            },
            "should_pass": True
        },
        {
            "name": "Dev Environment (Skipped)",
            "env": {
                "ENV": "dev",
                "JWT_SECRET": "weak",
                "COOKIES_SECURE": "0"
            },
            "should_pass": True
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_case['name']}")
        print("-" * 30)

        # Set environment
        original_env = {}
        for key, value in test_case['env'].items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value

        try:
            assert_strict_prod()
            if test_case.get('should_pass'):
                print("✅ PASSED: Config guard allowed configuration (as expected)")
            else:
                print("❌ FAILED: Config guard should have rejected configuration")
        except ConfigError as e:
            if test_case.get('should_pass'):
                print(f"❌ FAILED: Config guard rejected valid configuration: {e}")
            elif test_case.get('expected_error') in str(e):
                print(f"✅ PASSED: Config guard rejected configuration: {e}")
            else:
                print(f"❌ FAILED: Unexpected error: {e}")
        except Exception as e:
            print(f"❌ FAILED: Unexpected exception: {e}")
        finally:
            # Restore original environment
            for key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value

    print(f"\n{'=' * 50}")
    print("🎯 Config Guard Demo Complete!")
    print("\nKey Points:")
    print("- Production guardrails only run when ENV=prod and DEV_MODE is not set")
    print("- Weak configurations are rejected with clear ConfigError messages")
    print("- Dev mode bypasses all guardrails for development flexibility")
    print("- Valid production configs pass through successfully")
    print("- Non-prod environments skip guardrails entirely")


if __name__ == "__main__":
    demo_config_guard()
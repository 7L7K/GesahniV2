#!/usr/bin/env python3
"""
Debug script for authentication flow testing.
This script helps identify where the sign-in/login process is failing.
"""

import json
import logging
from typing import Any

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AuthDebugger:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    def test_health(self) -> bool:
        """Test if the server is running and healthy."""
        try:
            response = self.session.get(f"{self.base_url}/healthz/ready")
            logger.info(f"Health check: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def test_whoami_unauthenticated(self) -> dict[str, Any]:
        """Test whoami endpoint without authentication."""
        try:
            response = self.session.get(f"{self.base_url}/v1/whoami")
            logger.info(f"Whoami unauthenticated: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Whoami response: {json.dumps(data, indent=2)}")
                return data
            else:
                logger.error(f"Whoami failed: {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Whoami test failed: {e}")
            return {}

    def test_login(self, username: str, password: str) -> dict[str, Any]:
        """Test login endpoint."""
        try:
            payload = {"username": username, "password": password}
            logger.info(f"Attempting login for user: {username}")

            response = self.session.post(
                f"{self.base_url}/v1/login",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            logger.info(f"Login response status: {response.status_code}")
            logger.info(f"Login response headers: {dict(response.headers)}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Login successful: {json.dumps(data, indent=2)}")

                # Check for cookies
                cookies = dict(response.cookies)
                logger.info(f"Cookies received: {cookies}")

                return data
            else:
                logger.error(f"Login failed: {response.text}")
                return {}

        except Exception as e:
            logger.error(f"Login test failed: {e}")
            return {}

    def test_whoami_authenticated(self) -> dict[str, Any]:
        """Test whoami endpoint after authentication."""
        try:
            response = self.session.get(f"{self.base_url}/v1/whoami")
            logger.info(f"Whoami authenticated: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Whoami response: {json.dumps(data, indent=2)}")
                return data
            else:
                logger.error(f"Whoami failed: {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Whoami test failed: {e}")
            return {}

    def test_register(self, username: str, password: str) -> dict[str, Any]:
        """Test register endpoint."""
        try:
            payload = {"username": username, "password": password}
            logger.info(f"Attempting registration for user: {username}")

            response = self.session.post(
                f"{self.base_url}/v1/register",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            logger.info(f"Register response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"Registration successful: {json.dumps(data, indent=2)}")
                return data
            else:
                logger.error(f"Registration failed: {response.text}")
                return {}

        except Exception as e:
            logger.error(f"Registration test failed: {e}")
            return {}

    def run_full_test(self, username: str = "testuser", password: str = os.getenv("DEBUG_PASSWORD", "testpass123")):
        """Run a full authentication flow test."""
        logger.info("=" * 50)
        logger.info("Starting Authentication Debug Test")
        logger.info("=" * 50)

        # Test 1: Health check
        logger.info("\n1. Testing server health...")
        if not self.test_health():
            logger.error("Server is not healthy. Exiting.")
            return

        # Test 2: Whoami before authentication
        logger.info("\n2. Testing whoami before authentication...")
        self.test_whoami_unauthenticated()

        # Test 3: Registration
        logger.info("\n3. Testing registration...")
        self.test_register(username, password)

        # Test 4: Login
        logger.info("\n4. Testing login...")
        login_result = self.test_login(username, password)

        if not login_result:
            logger.error("Login failed. Cannot continue with authenticated tests.")
            return

        # Test 5: Whoami after authentication
        logger.info("\n5. Testing whoami after authentication...")
        self.test_whoami_authenticated()

        logger.info("\n" + "=" * 50)
        logger.info("Authentication Debug Test Complete")
        logger.info("=" * 50)


def main():
    """Main function to run the debug tests."""
    debugger = AuthDebugger()

    # You can customize these values
    username = "testuser"
    password = "testpass123"

    debugger.run_full_test(username, password)


if __name__ == "__main__":
    main()

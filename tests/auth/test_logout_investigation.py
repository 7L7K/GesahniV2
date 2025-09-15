#!/usr/bin/env python3
"""
Systematic test to identify which pages cause authentication logouts.
This script will test various endpoints and conditions to isolate the logout trigger.
"""

import time

import requests


class LogoutInvestigator:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
            }
        )

    def login_via_google_oauth_flow(self) -> bool:
        """Simulate the Google OAuth login flow"""
        print("🔐 Starting Google OAuth login simulation...")

        # Step 1: Get login URL
        login_url_endpoint = f"{self.base_url}/v1/google/auth/login_url?next=/"
        print(f"📡 Getting login URL from: {login_url_endpoint}")

        try:
            response = self.session.get(login_url_endpoint)
            if response.status_code != 200:
                print(f"❌ Failed to get login URL: {response.status_code}")
                return False

            login_data = response.json()
            print(f"✅ Got login URL: {login_data.get('login_url', 'N/A')[:100]}...")

            # Step 2: Simulate successful OAuth callback (we'll mock this)
            print("🔄 Simulating OAuth callback...")

            # This would normally happen after Google redirects back
            # For testing, we'll assume the callback sets the auth cookies

            return True

        except Exception as e:
            print(f"❌ Login simulation failed: {e}")
            return False

    def test_authentication_status(self) -> tuple[bool, dict]:
        """Test current authentication status"""
        whoami_url = f"{self.base_url}/v1/whoami"
        print(f"🔍 Checking auth status: {whoami_url}")

        try:
            response = self.session.get(whoami_url)
            data = response.json()

            is_authenticated = data.get("is_authenticated", False)
            user_id = data.get("user_id", None)

            print(f"📊 Auth Status: {is_authenticated}, User: {user_id}")

            return is_authenticated, data

        except Exception as e:
            print(f"❌ Auth check failed: {e}")
            return False, {}

    def test_endpoint(
        self, endpoint: str, method: str = "GET", data: dict = None
    ) -> dict:
        """Test a specific endpoint and check auth status"""
        url = f"{self.base_url}{endpoint}"
        print(f"🧪 Testing {method} {endpoint}")

        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                print(f"❌ Unsupported method: {method}")
                return {"error": f"Unsupported method: {method}"}

            # Check if this caused a redirect (potential logout)
            if response.status_code in [302, 401, 403]:
                print(f"⚠️  Potential logout trigger: {response.status_code}")

            # Get CSRF token if available
            csrf_token = None
            if "csrf_token" in response.cookies:
                csrf_token = response.cookies["csrf_token"]
                print(f"🍪 CSRF token: {csrf_token[:20]}...")

            return {
                "status_code": response.status_code,
                "redirect": (
                    response.is_redirect if hasattr(response, "is_redirect") else False
                ),
                "csrf_token": csrf_token,
                "location": response.headers.get("Location", None),
                "cookies": dict(response.cookies),
            }

        except Exception as e:
            print(f"❌ Endpoint test failed: {e}")
            return {"error": str(e)}

    def run_comprehensive_test(self):
        """Run comprehensive test of all endpoints and conditions"""

        print("🚀 Starting comprehensive logout investigation...")
        print("=" * 60)

        # Step 1: Check initial auth status
        print("\n1️⃣ Initial Authentication Status:")
        is_auth, auth_data = self.test_authentication_status()

        if not is_auth:
            print("❌ Not authenticated initially")
            return

        # Step 2: Test all public endpoints
        public_endpoints = [
            "/healthz/ready",
            "/healthz/deps",
            "/v1/whoami",
            "/v1/csrf",
            "/v1/budget",
            "/v1/profile",
            "/v1/integrations/status",
            "/v1/sessions",
            "/v1/pats",
            "/v1/ha_status",
        ]

        print("\n2️⃣ Testing Public Endpoints:")
        logout_triggers = []

        for endpoint in public_endpoints:
            result = self.test_endpoint(endpoint)

            if result.get("status_code") in [401, 403]:
                logout_triggers.append(
                    {
                        "endpoint": endpoint,
                        "reason": f"Status {result['status_code']}",
                        "details": result,
                    }
                )

            # Check auth status after each request
            auth_after, _ = self.test_authentication_status()
            if not auth_after:
                logout_triggers.append(
                    {
                        "endpoint": endpoint,
                        "reason": "Lost authentication",
                        "details": result,
                    }
                )
                print("🚨 LOGOUT DETECTED!")
                break

            time.sleep(0.1)  # Small delay between requests

        # Step 3: Test protected endpoints (should fail but not logout)
        protected_endpoints = [
            "/v1/admin/metrics",
            "/v1/admin/errors",
            "/v1/admin/self_review",
            "/v1/admin/router/decisions",
        ]

        print("\n3️⃣ Testing Protected Endpoints (should 403 but not logout):")

        for endpoint in protected_endpoints:
            result = self.test_endpoint(endpoint)

            if result.get("status_code") in [401]:  # 401 would indicate logout
                logout_triggers.append(
                    {
                        "endpoint": endpoint,
                        "reason": f"Unexpected logout on protected endpoint: {result['status_code']}",
                        "details": result,
                    }
                )

            # Check auth status after each request
            auth_after, _ = self.test_authentication_status()
            if not auth_after:
                logout_triggers.append(
                    {
                        "endpoint": endpoint,
                        "reason": "Lost authentication on protected endpoint",
                        "details": result,
                    }
                )
                print("🚨 LOGOUT DETECTED!")
                break

            time.sleep(0.1)

        # Step 4: Test POST endpoints
        post_endpoints = [
            ("/v1/ask", {"prompt": "hello"}),
            ("/v1/csrf", {}),  # This should be GET, but testing anyway
        ]

        print("\n4️⃣ Testing POST Endpoints:")

        for endpoint, data in post_endpoints:
            result = self.test_endpoint(endpoint, "POST", data)

            if result.get("status_code") in [401, 403]:
                logout_triggers.append(
                    {
                        "endpoint": endpoint,
                        "method": "POST",
                        "reason": f"Status {result['status_code']}",
                        "details": result,
                    }
                )

            # Check auth status after each request
            auth_after, _ = self.test_authentication_status()
            if not auth_after:
                logout_triggers.append(
                    {
                        "endpoint": endpoint,
                        "method": "POST",
                        "reason": "Lost authentication",
                        "details": result,
                    }
                )
                print("🚨 LOGOUT DETECTED!")
                break

            time.sleep(0.1)

        # Step 5: Test rapid requests (potential race condition)
        print("\n5️⃣ Testing Rapid Requests:")

        rapid_endpoints = ["/v1/whoami", "/v1/budget", "/v1/profile"]
        for i in range(5):
            print(f"  Rapid request {i+1}:")
            for endpoint in rapid_endpoints:
                result = self.test_endpoint(endpoint)

                auth_after, _ = self.test_authentication_status()
                if not auth_after:
                    logout_triggers.append(
                        {
                            "endpoint": endpoint,
                            "reason": f"Lost authentication on rapid request {i+1}",
                            "details": result,
                        }
                    )
                    print("🚨 LOGOUT DETECTED!")
                    break
            else:
                continue
            break

        # Step 6: Test with different headers
        print("\n6️⃣ Testing with different headers:")

        original_headers = self.session.headers.copy()

        # Test without User-Agent
        self.session.headers = {
            k: v for k, v in original_headers.items() if k != "User-Agent"
        }
        result = self.test_endpoint("/v1/whoami")
        auth_after, _ = self.test_authentication_status()
        if not auth_after:
            logout_triggers.append(
                {
                    "endpoint": "/v1/whoami",
                    "reason": "Lost authentication without User-Agent",
                    "details": result,
                }
            )

        # Restore headers
        self.session.headers = original_headers

        # Step 7: Summary
        print("\n" + "=" * 60)
        print("📋 INVESTIGATION SUMMARY:")
        print("=" * 60)

        if not logout_triggers:
            print("✅ No logout triggers found!")
            print("   All tested endpoints maintained authentication.")
        else:
            print(f"🚨 Found {len(logout_triggers)} potential logout triggers:")
            for i, trigger in enumerate(logout_triggers, 1):
                print(f"  {i}. {trigger['endpoint']}: {trigger['reason']}")

        print("\n🔍 Next steps:")
        print("   - Check frontend authentication handling")
        print("   - Examine CSRF token implementation")
        print("   - Verify cookie refresh mechanism")
        print("   - Test with actual browser automation")


def main():
    investigator = LogoutInvestigator()
    investigator.run_comprehensive_test()


if __name__ == "__main__":
    main()

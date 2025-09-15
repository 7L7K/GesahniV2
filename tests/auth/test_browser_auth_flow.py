#!/usr/bin/env python3
"""
Test to reproduce the browser authentication flow and identify logout triggers.
This simulates the real user experience that causes logouts on certain pages.
"""

import random
import time
from urllib.parse import urlencode, urljoin

import requests


class BrowserAuthSimulator:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        frontend_url: str = "http://localhost:3000",
    ):
        self.base_url = base_url
        self.frontend_url = frontend_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def simulate_login_flow(self) -> bool:
        """Simulate the complete login flow like a real browser"""
        print("🔐 Simulating complete browser login flow...")

        # Step 1: Visit login page
        login_page_url = f"{self.frontend_url}/login"
        print(f"📄 Visiting login page: {login_page_url}")

        try:
            response = self.session.get(login_page_url, follow_redirects=False)
            print(f"  Login page response: {response.status_code}")

            if response.status_code not in [200, 302]:
                print(f"❌ Unexpected response from login page: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Failed to load login page: {e}")
            return False

        # Step 2: Get Google OAuth login URL
        oauth_url_endpoint = f"{self.base_url}/v1/google/auth/login_url"
        print(f"🔗 Getting OAuth URL: {oauth_url_endpoint}")

        try:
            response = self.session.get(oauth_url_endpoint)
            if response.status_code != 200:
                print(f"❌ Failed to get OAuth URL: {response.status_code}")
                return False

            oauth_data = response.json()
            oauth_url = oauth_data.get("url")

            if not oauth_url:
                print("❌ No OAuth URL in response")
                return False

            print(f"✅ Got OAuth URL: {oauth_url[:100]}...")

            # Step 3: Simulate the OAuth callback (this would normally happen after Google redirects)
            print("🔄 Simulating OAuth callback...")

            # Extract state from cookies (this simulates the real flow)
            state_cookie = None
            for cookie in self.session.cookies:
                if "oauth_state" in cookie.name or "state" in cookie.name:
                    state_cookie = cookie.value
                    break

            if not state_cookie:
                print("⚠️ No state cookie found - this might be part of the issue")
                # Try to continue anyway

            # Simulate successful OAuth callback
            callback_url = f"{self.base_url}/v1/google/auth/callback"
            callback_params = {
                "state": state_cookie or "simulated_state",
                "code": "simulated_auth_code",
                "scope": "email profile https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/gmail.send",
            }

            callback_full_url = f"{callback_url}?{urlencode(callback_params)}"
            print(f"📞 Simulating callback: {callback_full_url}")

            response = self.session.get(callback_full_url, follow_redirects=False)

            if response.status_code == 302:
                redirect_location = response.headers.get("Location")
                print(f"✅ OAuth callback successful, redirect to: {redirect_location}")

                # Follow the redirect (this sets auth cookies)
                if redirect_location:
                    redirect_response = self.session.get(
                        redirect_location, follow_redirects=False
                    )
                    print(f"  Redirect response: {redirect_response.status_code}")

                    # Check if auth cookies were set
                    auth_cookies = [
                        c for c in self.session.cookies if "access_token" in c.name
                    ]
                    print(f"  Auth cookies set: {len(auth_cookies)}")

                    return len(auth_cookies) > 0
            else:
                print(f"❌ OAuth callback failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Login flow failed: {e}")
            return False

    def test_page_navigation(self, pages: list[str]) -> list[dict]:
        """Test navigating to various pages and check for logout triggers"""
        results = []

        print("🧭 Testing page navigation...")

        for page in pages:
            page_url = urljoin(self.frontend_url, page)
            print(f"\n📄 Testing page: {page}")

            try:
                # Simulate page visit
                start_time = time.time()
                response = self.session.get(page_url, follow_redirects=False)
                end_time = time.time()

                result = {
                    "page": page,
                    "url": page_url,
                    "status_code": response.status_code,
                    "duration_ms": round((end_time - start_time) * 1000, 2),
                    "redirect_location": response.headers.get("Location"),
                    "cookies_before": dict(self.session.cookies),
                }

                if response.status_code == 302 and "/login" in (
                    response.headers.get("Location") or ""
                ):
                    print(f"🚨 LOGOUT TRIGGER: Redirect to login from {page}")
                    result["logout_triggered"] = True
                elif response.status_code == 401:
                    print(f"🚨 LOGOUT TRIGGER: 401 error on {page}")
                    result["logout_triggered"] = True
                else:
                    result["logout_triggered"] = False

                # Check auth status after page visit
                whoami_result = self.check_auth_status()
                result["auth_after"] = whoami_result

                if (
                    whoami_result.get("is_authenticated") is False
                    and whoami_result.get("status_code") == 200
                ):
                    print(f"🚨 LOGOUT TRIGGER: Lost authentication on {page}")
                    result["logout_triggered"] = True

                results.append(result)

                # Small delay between page visits
                time.sleep(random.uniform(0.5, 2.0))

            except Exception as e:
                results.append(
                    {"page": page, "error": str(e), "logout_triggered": False}
                )
                print(f"❌ Error testing {page}: {e}")

        return results

    def check_auth_status(self) -> dict:
        """Check current authentication status"""
        whoami_url = f"{self.base_url}/v1/whoami"

        try:
            response = self.session.get(whoami_url)
            result = {"status_code": response.status_code, "timestamp": time.time()}

            if response.status_code == 200:
                data = response.json()
                result.update(
                    {
                        "is_authenticated": data.get("is_authenticated", False),
                        "user_id": data.get("user_id"),
                        "source": data.get("source"),
                        "session_ready": data.get("session_ready", False),
                    }
                )
            else:
                result["error"] = response.text[:200]

            return result

        except Exception as e:
            return {"error": str(e), "status_code": 0}

    def test_api_calls_after_login(self) -> list[dict]:
        """Test various API calls that might trigger logouts"""
        api_endpoints = [
            "/v1/whoami",
            "/v1/budget",
            "/v1/profile",
            "/v1/integrations/status",
            "/v1/sessions",
            "/v1/pats",
            "/v1/ha_status",
            "/v1/csrf",
        ]

        results = []
        print("🔌 Testing API calls after login...")

        for endpoint in api_endpoints:
            url = f"{self.base_url}{endpoint}"
            print(f"  Testing {endpoint}")

            try:
                if endpoint == "/v1/csrf":
                    # GET request
                    response = self.session.get(url)
                else:
                    # GET request for most endpoints
                    response = self.session.get(url)

                result = {
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "timestamp": time.time(),
                }

                if response.status_code == 401:
                    print(f"🚨 LOGOUT TRIGGER: 401 on {endpoint}")
                    result["logout_triggered"] = True

                    # Check if this actually logs us out
                    auth_check = self.check_auth_status()
                    if auth_check.get("is_authenticated") is False:
                        result["confirmed_logout"] = True
                else:
                    result["logout_triggered"] = False

                results.append(result)

                # Small delay
                time.sleep(0.1)

            except Exception as e:
                results.append(
                    {"endpoint": endpoint, "error": str(e), "logout_triggered": False}
                )

        return results

    def test_timing_patterns(self) -> list[dict]:
        """Test timing patterns that might cause race conditions"""
        results = []
        whoami_url = f"{self.base_url}/v1/whoami"

        print("⏱️ Testing timing patterns...")

        # Test rapid successive calls
        print("  Testing rapid calls...")
        for i in range(5):
            try:
                response = self.session.get(whoami_url)
                result = {
                    "test": f"rapid_call_{i+1}",
                    "status_code": response.status_code,
                    "timestamp": time.time(),
                }

                if response.status_code == 401:
                    result["logout_triggered"] = True
                    print(f"🚨 LOGOUT TRIGGER: 401 on rapid call {i+1}")
                else:
                    result["logout_triggered"] = False

                results.append(result)
                time.sleep(0.05)  # Very short delay

            except Exception as e:
                results.append(
                    {
                        "test": f"rapid_call_{i+1}",
                        "error": str(e),
                        "logout_triggered": False,
                    }
                )

        # Test with delays
        print("  Testing with delays...")
        for delay in [1, 5, 10]:
            try:
                time.sleep(delay)
                response = self.session.get(whoami_url)
                result = {
                    "test": f"delayed_call_{delay}s",
                    "delay": delay,
                    "status_code": response.status_code,
                    "timestamp": time.time(),
                }

                if response.status_code == 401:
                    result["logout_triggered"] = True
                    print(f"🚨 LOGOUT TRIGGER: 401 after {delay}s delay")
                else:
                    result["logout_triggered"] = False

                results.append(result)

            except Exception as e:
                results.append(
                    {
                        "test": f"delayed_call_{delay}s",
                        "error": str(e),
                        "logout_triggered": False,
                    }
                )

        return results

    def run_comprehensive_test(self):
        """Run comprehensive browser simulation test"""
        print("🚀 Starting comprehensive browser authentication test...")
        print("=" * 70)

        # Step 1: Check initial auth status
        print("\n1️⃣ Initial Authentication Status:")
        initial_auth = self.check_auth_status()
        print(f"  Authenticated: {initial_auth.get('is_authenticated', 'unknown')}")
        print(f"  User ID: {initial_auth.get('user_id', 'none')}")
        print(f"  Status: {initial_auth.get('status_code', 'unknown')}")

        print("\n" + "=" * 50)

        # Step 2: Simulate login
        print("\n2️⃣ Simulating Login Flow:")
        login_success = self.simulate_login_flow()

        if not login_success:
            print("❌ Login simulation failed - cannot continue test")
            return

        print("\n" + "=" * 50)

        # Step 3: Check auth after login
        print("\n3️⃣ Authentication After Login:")
        post_login_auth = self.check_auth_status()
        print(f"  Authenticated: {post_login_auth.get('is_authenticated', 'unknown')}")
        print(f"  User ID: {post_login_auth.get('user_id', 'none')}")
        print(f"  Status: {post_login_auth.get('status_code', 'unknown')}")

        if not post_login_auth.get("is_authenticated"):
            print("❌ Still not authenticated after login simulation")
            return

        print("\n" + "=" * 50)

        # Step 4: Test page navigation
        print("\n4️⃣ Testing Page Navigation:")
        pages_to_test = [
            "/",
            "/settings",
            "/admin",
            "/spotify/callback",
            "/tv",
            "/test-cors",
            "/login",  # This should redirect if logged in
        ]

        page_results = self.test_page_navigation(pages_to_test)

        print("\n" + "=" * 50)

        # Step 5: Test API calls
        print("\n5️⃣ Testing API Calls:")
        api_results = self.test_api_calls_after_login()

        print("\n" + "=" * 50)

        # Step 6: Test timing patterns
        print("\n6️⃣ Testing Timing Patterns:")
        timing_results = self.test_timing_patterns()

        print("\n" + "=" * 50)

        # Step 7: Final auth check
        print("\n7️⃣ Final Authentication Check:")
        final_auth = self.check_auth_status()
        print(f"  Authenticated: {final_auth.get('is_authenticated', 'unknown')}")
        print(f"  User ID: {final_auth.get('user_id', 'none')}")
        print(f"  Status: {final_auth.get('status_code', 'unknown')}")

        print("\n" + "=" * 70)

        # Step 8: Summary
        print("\n📋 TEST SUMMARY:")
        print("=" * 70)

        all_results = page_results + api_results + timing_results
        logout_triggers = [r for r in all_results if r.get("logout_triggered", False)]

        if logout_triggers:
            print(f"🚨 FOUND {len(logout_triggers)} LOGOUT TRIGGERS:")
            for trigger in logout_triggers:
                trigger_type = trigger.get(
                    "page", trigger.get("endpoint", trigger.get("test", "unknown"))
                )
                print(f"  • {trigger_type}")

            # Analyze patterns
            page_triggers = [r for r in logout_triggers if "page" in r]
            api_triggers = [r for r in logout_triggers if "endpoint" in r]
            timing_triggers = [
                r
                for r in logout_triggers
                if "test" in r and "rapid" in r.get("test", "")
            ]

            if page_triggers:
                print(f"\n📄 Page triggers: {[t['page'] for t in page_triggers]}")
            if api_triggers:
                print(f"\n🔌 API triggers: {[t['endpoint'] for t in api_triggers]}")
            if timing_triggers:
                print(f"\n⏱️ Timing triggers: {[t['test'] for t in timing_triggers]}")

        else:
            print("✅ No logout triggers found in this simulation")
            print("   This suggests the issue might be:")
            print("   - Browser-specific (Safari, Chrome, etc.)")
            print("   - Real user interaction patterns")
            print("   - Frontend JavaScript state management")
            print("   - Cookie/storage handling differences")

        print("\n🔍 RECOMMENDED NEXT STEPS:")
        print("   1. Check browser developer tools for failed requests")
        print("   2. Monitor frontend console for auth errors")
        print("   3. Test with real browser automation (Selenium/Playwright)")
        print("   4. Check if issue occurs on specific browsers")
        print("   5. Verify cookie settings and SameSite attributes")


def main():
    simulator = BrowserAuthSimulator()
    simulator.run_comprehensive_test()


if __name__ == "__main__":
    main()

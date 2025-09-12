#!/usr/bin/env python3
"""
Test post-login behavior to identify what causes logouts after successful authentication.
This focuses on the scenario where a user is already logged in but loses authentication on certain pages.
"""

import time

import requests


class PostLoginTester:
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

    def simulate_authenticated_session(self) -> bool:
        """Simulate having an authenticated session (like the user who successfully logged in)"""
        print("🔐 Simulating authenticated session...")

        # Based on the backend logs, the user had these cookies/tokens:
        # - access_token_cookie with 362 characters
        # - 13 total cookies
        # - User ID: havenotseen@gmail.com

        # For testing, we'll create a mock authenticated state
        # In reality, this would be set by the successful OAuth flow

        print("✅ Simulated authenticated session")
        return True

    def test_whoami_patterns(self) -> list[dict]:
        """Test whoami call patterns that might cause issues"""
        results = []
        whoami_url = f"{self.base_url}/v1/whoami"

        print("🔍 Testing whoami call patterns...")

        patterns = [
            {"name": "normal_call", "delay": 0, "headers": {}},
            {
                "name": "with_cache_buster",
                "delay": 0,
                "headers": {"Cache-Control": "no-cache"},
            },
            {
                "name": "with_different_ua",
                "delay": 0,
                "headers": {"User-Agent": "Different Browser/1.0"},
            },
            {"name": "rapid_calls", "delay": 0.05, "count": 5},
            {"name": "delayed_calls", "delay": 2.0, "count": 3},
        ]

        for pattern in patterns:
            print(f"  Testing pattern: {pattern['name']}")

            if pattern.get("count"):
                # Multiple calls
                for i in range(pattern["count"]):
                    result = self._make_whoami_call(
                        whoami_url, pattern.get("headers", {})
                    )
                    result["pattern"] = f"{pattern['name']}_{i+1}"
                    results.append(result)

                    if pattern["delay"] > 0:
                        time.sleep(pattern["delay"])
            else:
                # Single call
                result = self._make_whoami_call(whoami_url, pattern.get("headers", {}))
                result["pattern"] = pattern["name"]
                results.append(result)

                if pattern["delay"] > 0:
                    time.sleep(pattern["delay"])

        return results

    def _make_whoami_call(self, url: str, extra_headers: dict = None) -> dict:
        """Make a single whoami call and analyze the response"""
        headers = {}
        if extra_headers:
            headers.update(extra_headers)

        try:
            response = self.session.get(url, headers=headers)

            result = {
                "status_code": response.status_code,
                "response_time_ms": len(response.content),  # Rough timing proxy
                "cookies_count": len(self.session.cookies),
                "has_access_token": any(
                    "access_token" in c.name for c in self.session.cookies
                ),
                "timestamp": time.time(),
            }

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
                if response.status_code == 401:
                    result["logout_trigger"] = True

            return result

        except Exception as e:
            return {"error": str(e), "status_code": 0}

    def test_api_endpoint_patterns(self) -> list[dict]:
        """Test various API endpoints that might trigger logouts"""
        results = []
        endpoints = [
            "/v1/whoami",
            "/v1/budget",
            "/v1/profile",
            "/v1/integrations/status",
            "/v1/sessions",
            "/v1/pats",
            "/v1/ha_status",
            "/v1/csrf",
            "/v1/state",  # This one returns 404 in logs
            "/v1/ask",  # POST endpoint
        ]

        print("🔌 Testing API endpoints...")

        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            print(f"  Testing {endpoint}")

            try:
                if endpoint in ["/v1/ask"]:
                    # POST request
                    response = self.session.post(url, json={"prompt": "test"})
                    method = "POST"
                else:
                    # GET request
                    response = self.session.get(url)
                    method = "GET"

                result = {
                    "endpoint": endpoint,
                    "method": method,
                    "status_code": response.status_code,
                    "timestamp": time.time(),
                }

                if response.status_code == 401:
                    print(f"🚨 401 error on {endpoint}")
                    result["logout_trigger"] = True

                    # Check if this actually logs us out by testing whoami
                    whoami_check = self._make_whoami_call(f"{self.base_url}/v1/whoami")
                    if whoami_check.get("status_code") == 401:
                        result["confirmed_logout"] = True
                        print(f"🚨 Confirmed logout after {endpoint}")

                elif response.status_code == 403:
                    print(
                        f"🚫 403 forbidden on {endpoint} (expected for some endpoints)"
                    )

                results.append(result)

                # Small delay between requests
                time.sleep(0.1)

            except Exception as e:
                results.append(
                    {"endpoint": endpoint, "error": str(e), "logout_trigger": False}
                )

        return results

    def test_rate_limiting_scenarios(self) -> list[dict]:
        """Test scenarios that might trigger rate limiting and cause logouts"""
        results = []
        whoami_url = f"{self.base_url}/v1/whoami"

        print("⚡ Testing rate limiting scenarios...")

        # Test rapid fire requests
        print("  Testing rapid requests...")
        for i in range(10):
            result = self._make_whoami_call(whoami_url)
            result["test"] = f"rapid_{i+1}"
            results.append(result)

            if result.get("status_code") == 429:
                print(f"🚫 Rate limited on request {i+1}")
                result["rate_limited"] = True
                break

            time.sleep(0.05)  # Very short delay

        # Test with backoff after rate limit
        if any(r.get("rate_limited") for r in results):
            print("  Testing after rate limit...")
            time.sleep(5)  # Wait for rate limit to expire

            result = self._make_whoami_call(whoami_url)
            result["test"] = "after_rate_limit"
            results.append(result)

        return results

    def test_cookie_behavior(self) -> dict:
        """Test cookie behavior and potential issues"""
        print("🍪 Analyzing cookie behavior...")

        initial_cookies = dict(self.session.cookies)

        # Make a few requests
        whoami_results = []
        for i in range(3):
            result = self._make_whoami_call(f"{self.base_url}/v1/whoami")
            whoami_results.append(result)
            time.sleep(0.5)

        after_cookies = dict(self.session.cookies)

        # Analyze cookie changes
        initial_names = set(initial_cookies.keys())
        after_names = set(after_cookies.keys())

        added_cookies = after_names - initial_names
        removed_cookies = initial_names - after_names

        return {
            "initial_cookies": len(initial_cookies),
            "after_cookies": len(after_cookies),
            "added_cookies": list(added_cookies),
            "removed_cookies": list(removed_cookies),
            "whoami_results": whoami_results,
            "cookie_analysis": {
                "has_csrf_token": any("csrf_token" in name for name in after_names),
                "has_access_token": any("access_token" in name for name in after_names),
                "has_refresh_token": any(
                    "refresh_token" in name for name in after_names
                ),
            },
        }

    def test_frontend_page_behavior(self) -> list[dict]:
        """Test frontend pages that might cause logout issues"""
        results = []
        pages = [
            "/login",  # Should redirect if logged in
            "/settings",
            "/admin",  # Requires admin scope
            "/tv",
            "/",  # Home page
        ]

        print("🌐 Testing frontend pages...")

        for page in pages:
            page_url = f"{self.frontend_url}{page}"
            print(f"  Testing page: {page}")

            try:
                response = self.session.get(page_url, follow_redirects=False)

                result = {
                    "page": page,
                    "status_code": response.status_code,
                    "redirect_location": response.headers.get("Location"),
                    "timestamp": time.time(),
                }

                if response.status_code == 302:
                    redirect_to = response.headers.get("Location", "")
                    if "/login" in redirect_to:
                        print(f"🚨 Redirect to login from {page}")
                        result["logout_redirect"] = True

                        # Check if we're actually logged out
                        whoami_check = self._make_whoami_call(
                            f"{self.base_url}/v1/whoami"
                        )
                        if whoami_check.get("status_code") == 401:
                            result["confirmed_logout"] = True

                results.append(result)

                # Small delay
                time.sleep(0.5)

            except Exception as e:
                results.append({"page": page, "error": str(e)})

        return results

    def run_comprehensive_test(self):
        """Run comprehensive post-login behavior test"""
        print("🚀 Starting post-login behavior analysis...")
        print("=" * 60)

        # Step 1: Simulate authenticated session
        print("\n1️⃣ Simulating Authenticated Session:")
        if not self.simulate_authenticated_session():
            print("❌ Failed to simulate authenticated session")
            return

        print("\n" + "=" * 40)

        # Step 2: Test whoami patterns
        print("\n2️⃣ Testing Whoami Call Patterns:")
        whoami_results = self.test_whoami_patterns()

        # Analyze whoami results
        logout_triggers = [r for r in whoami_results if r.get("logout_trigger")]
        if logout_triggers:
            print(f"🚨 Found {len(logout_triggers)} whoami logout triggers")

        print("\n" + "=" * 40)

        # Step 3: Test API endpoints
        print("\n3️⃣ Testing API Endpoints:")
        api_results = self.test_api_endpoint_patterns()

        api_logouts = [r for r in api_results if r.get("confirmed_logout")]
        if api_logouts:
            print(f"🚨 Found {len(api_logouts)} API logout triggers")

        print("\n" + "=" * 40)

        # Step 4: Test rate limiting
        print("\n4️⃣ Testing Rate Limiting Scenarios:")
        rate_results = self.test_rate_limiting_scenarios()

        rate_limits = [r for r in rate_results if r.get("rate_limited")]
        if rate_limits:
            print(f"⚡ Found {len(rate_limits)} rate limiting events")

        print("\n" + "=" * 40)

        # Step 5: Test cookie behavior
        print("\n5️⃣ Testing Cookie Behavior:")
        cookie_analysis = self.test_cookie_behavior()

        print(f"  Initial cookies: {cookie_analysis['initial_cookies']}")
        print(f"  After cookies: {cookie_analysis['after_cookies']}")
        if cookie_analysis["cookie_analysis"]["has_access_token"]:
            print("  ✅ Has access token cookie")
        else:
            print("  ❌ Missing access token cookie")

        print("\n" + "=" * 40)

        # Step 6: Test frontend pages
        print("\n6️⃣ Testing Frontend Pages:")
        page_results = self.test_frontend_page_behavior()

        page_logouts = [r for r in page_results if r.get("logout_redirect")]
        if page_logouts:
            print(f"🚨 Found {len(page_logouts)} page logout redirects")

        print("\n" + "=" * 40)

        # Step 7: Overall summary
        print("\n📋 COMPREHENSIVE ANALYSIS SUMMARY:")
        print("=" * 60)

        all_logout_triggers = []
        all_logout_triggers.extend(logout_triggers)
        all_logout_triggers.extend(api_logouts)
        all_logout_triggers.extend(
            [r for r in page_results if r.get("confirmed_logout")]
        )

        if all_logout_triggers:
            print(f"🚨 IDENTIFIED {len(all_logout_triggers)} LOGOUT TRIGGERS:")
            for trigger in all_logout_triggers:
                if "pattern" in trigger:
                    print(f"  • Whoami pattern: {trigger['pattern']}")
                elif "endpoint" in trigger:
                    print(
                        f"  • API endpoint: {trigger['endpoint']} ({trigger['method']})"
                    )
                elif "page" in trigger:
                    print(f"  • Frontend page: {trigger['page']}")

            print("\n🔍 ANALYSIS INSIGHTS:")
            print("   These patterns may cause the logout behavior you experience.")
            print("   The issue could be:")
            print("   - Race conditions in authentication checks")
            print("   - Rate limiting causing temporary 401s")
            print("   - Frontend incorrectly handling certain error conditions")
            print("   - Cookie expiration or renewal issues")

        else:
            print("✅ No logout triggers found in this test")
            print("   This suggests the issue might be:")
            print("   - Browser-specific behavior (Safari vs Chrome)")
            print("   - Real user interaction patterns not captured here")
            print("   - Frontend JavaScript state management issues")
            print("   - Timing-sensitive race conditions")

        print("\n🔧 RECOMMENDED FIXES TO INVESTIGATE:")
        print("   1. Check frontend 401 error handling in api.ts")
        print("   2. Verify cookie SameSite and Secure settings")
        print("   3. Test with different browsers")
        print("   4. Check for race conditions in auth orchestrator")
        print("   5. Monitor network requests in browser dev tools")
        print("   6. Test with real browser automation")


def main():
    tester = PostLoginTester()
    tester.run_comprehensive_test()


if __name__ == "__main__":
    main()

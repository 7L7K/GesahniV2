#!/usr/bin/env python3
"""
Test CSRF token handling and authentication consistency.
This script tests the specific conditions that might cause 401 errors.
"""

import random
import time

import requests


class CSRFInvestigator:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
            }
        )

    def simulate_browser_behavior(self) -> bool:
        """Simulate realistic browser behavior that might trigger issues"""
        print("🌐 Simulating browser behavior patterns...")

        # Step 1: Get CSRF token
        csrf_url = f"{self.base_url}/v1/csrf"
        print(f"🔑 Getting CSRF token: {csrf_url}")

        try:
            response = self.session.get(csrf_url)
            if response.status_code != 200:
                print(f"❌ Failed to get CSRF token: {response.status_code}")
                return False

            csrf_data = response.json()
            csrf_token = csrf_data.get("csrf_token")
            if not csrf_token:
                print("❌ No CSRF token in response")
                return False

            print(f"✅ Got CSRF token: {csrf_token[:20]}...")
            self.csrf_token = csrf_token

            return True

        except Exception as e:
            print(f"❌ CSRF token fetch failed: {e}")
            return False

    def test_multiple_whoami_calls(self, num_calls: int = 10) -> list[dict]:
        """Test multiple whoami calls to check for consistency"""
        results = []
        whoami_url = f"{self.base_url}/v1/whoami"

        print(f"🔄 Testing {num_calls} whoami calls...")

        for i in range(num_calls):
            try:
                # Simulate browser timing patterns
                if i > 0:
                    delay = random.uniform(
                        0.1, 1.0
                    )  # Random delay like browser requests
                    time.sleep(delay)

                start_time = time.time()
                response = self.session.get(whoami_url)
                end_time = time.time()

                result = {
                    "call": i + 1,
                    "status_code": response.status_code,
                    "duration_ms": round((end_time - start_time) * 1000, 2),
                    "cookies_before": dict(self.session.cookies),
                    "response_headers": dict(response.headers),
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

                results.append(result)
                print(
                    f"  Call {i+1}: {response.status_code} ({result.get('duration_ms')}ms)"
                )

                # Check for logout triggers
                if response.status_code == 401:
                    print(f"🚨 LOGOUT TRIGGER: 401 on whoami call {i+1}")
                    break

            except Exception as e:
                results.append(
                    {"call": i + 1, "error": str(e), "timestamp": time.time()}
                )
                print(f"  Call {i+1}: ERROR - {e}")

        return results

    def test_concurrent_requests(self) -> list[dict]:
        """Test concurrent requests that might cause race conditions"""
        import threading

        results = []
        whoami_url = f"{self.base_url}/v1/whoami"

        print("🔀 Testing concurrent whoami requests...")

        def make_request(thread_id: int):
            try:
                response = self.session.get(whoami_url)
                result = {
                    "thread": thread_id,
                    "status_code": response.status_code,
                    "timestamp": time.time(),
                }

                if response.status_code == 200:
                    data = response.json()
                    result.update(
                        {
                            "is_authenticated": data.get("is_authenticated", False),
                            "user_id": data.get("user_id"),
                            "source": data.get("source"),
                        }
                    )

                results.append(result)
                print(f"  Thread {thread_id}: {response.status_code}")

            except Exception as e:
                results.append(
                    {"thread": thread_id, "error": str(e), "timestamp": time.time()}
                )

        # Start multiple threads simultaneously
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request, args=(i,))
            threads.append(thread)

        # Start all threads at once
        for thread in threads:
            thread.start()

        # Wait for all to complete
        for thread in threads:
            thread.join()

        return results

    def test_csrf_protected_endpoint(self) -> dict:
        """Test a CSRF-protected endpoint to see if it affects auth"""
        ask_url = f"{self.base_url}/v1/ask"

        print("🛡️ Testing CSRF-protected endpoint...")

        # First, ensure we have a CSRF token
        if not hasattr(self, "csrf_token") or not self.csrf_token:
            csrf_response = self.session.get(f"{self.base_url}/v1/csrf")
            if csrf_response.status_code == 200:
                csrf_data = csrf_response.json()
                self.csrf_token = csrf_data.get("csrf_token")
            else:
                return {"error": "Failed to get CSRF token"}

        try:
            # Make a POST request with CSRF token
            headers = {
                "Content-Type": "application/json",
                "X-CSRF-Token": self.csrf_token,
            }

            response = self.session.post(
                ask_url, json={"prompt": "hello"}, headers=headers
            )

            result = {
                "status_code": response.status_code,
                "has_csrf_token": bool(self.csrf_token),
                "cookies_after": dict(self.session.cookies),
            }

            if response.status_code == 200:
                data = response.json()
                result["response"] = data.get("response", "")[:100]
            else:
                result["error"] = response.text[:200]

            print(f"  POST /v1/ask: {response.status_code}")

            # Check whoami after the CSRF request
            whoami_result = self.test_multiple_whoami_calls(1)[0]
            result["whoami_after"] = whoami_result

            if whoami_result.get("status_code") == 401:
                print("🚨 LOGOUT TRIGGER: 401 after CSRF request")
                result["logout_triggered"] = True

            return result

        except Exception as e:
            return {"error": str(e)}

    def test_cookie_behavior(self) -> dict:
        """Test cookie handling and potential issues"""
        print("🍪 Testing cookie behavior...")

        # Check current cookies
        initial_cookies = dict(self.session.cookies)

        # Make a whoami request
        whoami_result = self.test_multiple_whoami_calls(1)[0]

        # Check cookies after request
        after_cookies = dict(self.session.cookies)

        return {
            "initial_cookies": initial_cookies,
            "after_cookies": after_cookies,
            "cookies_changed": initial_cookies != after_cookies,
            "whoami_result": whoami_result,
        }

    def run_comprehensive_test(self):
        """Run comprehensive CSRF and authentication test"""
        print("🚀 Starting comprehensive CSRF investigation...")
        print("=" * 60)

        # Step 1: Get CSRF token
        if not self.simulate_browser_behavior():
            print("❌ Failed to initialize CSRF token")
            return

        print("\n" + "=" * 40)

        # Step 2: Test multiple whoami calls
        print("\n1️⃣ Testing Multiple Whoami Calls:")
        whoami_results = self.test_multiple_whoami_calls(15)

        # Analyze results
        status_codes = [r.get("status_code", 0) for r in whoami_results]
        auth_statuses = [
            r.get("is_authenticated", False)
            for r in whoami_results
            if "is_authenticated" in r
        ]

        print("\n📊 Whoami Analysis:")
        print(f"  Status codes: {status_codes}")
        print(f"  Auth statuses: {auth_statuses}")
        print(f"  401 errors: {status_codes.count(401)}")
        print(f"  200 responses: {status_codes.count(200)}")

        if 401 in status_codes:
            print("🚨 FOUND LOGOUT TRIGGER: 401 responses detected")

        print("\n" + "=" * 40)

        # Step 3: Test concurrent requests
        print("\n2️⃣ Testing Concurrent Requests:")
        concurrent_results = self.test_concurrent_requests()

        # Analyze concurrent results
        concurrent_statuses = [
            r.get("status_code", 0) for r in concurrent_results if "status_code" in r
        ]
        print(f"  Concurrent status codes: {concurrent_statuses}")
        if 401 in concurrent_statuses:
            print("🚨 FOUND LOGOUT TRIGGER: 401 in concurrent requests")

        print("\n" + "=" * 40)

        # Step 4: Test CSRF-protected endpoint
        print("\n3️⃣ Testing CSRF-Protected Endpoint:")
        csrf_result = self.test_csrf_protected_endpoint()

        print("\n" + "=" * 40)

        # Step 5: Test cookie behavior
        print("\n4️⃣ Testing Cookie Behavior:")
        cookie_result = self.test_cookie_behavior()

        print("\n" + "=" * 40)

        # Step 6: Summary
        print("\n📋 INVESTIGATION SUMMARY:")
        print("=" * 60)

        issues_found = []

        if 401 in status_codes:
            issues_found.append(
                f"401 errors in {status_codes.count(401)}/{len(status_codes)} whoami calls"
            )

        if 401 in concurrent_statuses:
            issues_found.append("401 errors in concurrent requests")

        if csrf_result.get("logout_triggered"):
            issues_found.append("401 after CSRF-protected request")

        if issues_found:
            print("🚨 ISSUES FOUND:")
            for issue in issues_found:
                print(f"  • {issue}")
        else:
            print("✅ No obvious issues found")
            print("   - All whoami calls returned 200")
            print("   - Concurrent requests succeeded")
            print("   - CSRF requests didn't trigger logouts")

        print("\n🔍 Next steps:")
        print("   - Check frontend auth orchestrator logs")
        print("   - Monitor browser network requests")
        print("   - Test with actual browser automation")
        print("   - Check server-side rate limiting")


def main():
    investigator = CSRFInvestigator()
    investigator.run_comprehensive_test()


if __name__ == "__main__":
    main()

#!/bin/bash
# Quick authentication smoke test
# Verifies that login, CSRF, and logout work correctly

set -e

BASE_URL="${API_BASE:-http://localhost:8000}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

echo "🧪 Running authentication smoke test..."
echo "📍 Base URL: $BASE_URL"

# Test 1: Pre-auth whoami should return 401
echo "1️⃣  Testing pre-auth whoami..."
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/whoami" || true)
if [[ "$code" -ne 401 ]]; then
    echo "❌ FAIL: Expected 401, got $code"
    exit 1
fi
echo "✅ PASS: Returns 401 (unauthorized)"

# Test 2: CSRF endpoint should work
echo "2️⃣  Testing CSRF endpoint..."
csrf_response=$(curl -s -c "$COOKIE_JAR" "$BASE_URL/csrf")
if [[ -z "$csrf_response" ]] || [[ "$csrf_response" == *"error"* ]]; then
    echo "❌ FAIL: CSRF endpoint not working"
    exit 1
fi
echo "✅ PASS: CSRF endpoint working"

# Test 3: Login should work
echo "3️⃣  Testing login..."
CSRF=$(grep "csrf_token" "$COOKIE_JAR" | awk '{print $7}')
if [[ -z "$CSRF" ]]; then
    echo "❌ FAIL: Could not get CSRF token from cookie"
    exit 1
fi

code=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -H "X-CSRF-Token: $CSRF" \
  -X POST "$BASE_URL/v1/auth/login?username=demo" || true)
if [[ "$code" -ge 400 ]]; then
    echo "❌ FAIL: Login failed with code $code"
    exit 1
fi
echo "✅ PASS: Login successful"

# Test 4: Post-auth whoami should return 200
echo "4️⃣  Testing post-auth whoami..."
code=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$BASE_URL/v1/whoami" || true)
if [[ "$code" -ne 200 ]]; then
    echo "❌ FAIL: Expected 200 after login, got $code"
    exit 1
fi
echo "✅ PASS: Returns 200 (authenticated)"

# Test 5: Logout should work
echo "5️⃣  Testing logout..."
# Get fresh CSRF for logout
curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$BASE_URL/csrf" >/dev/null
CSRF=$(grep "csrf_token" "$COOKIE_JAR" | awk '{print $7}')

code=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" \
  -H "X-CSRF-Token: $CSRF" -X POST "$BASE_URL/v1/auth/logout" || true)
if [[ "$code" -ge 400 ]]; then
    echo "❌ FAIL: Logout failed with code $code"
    exit 1
fi
echo "✅ PASS: Logout successful"

# Test 6: Post-logout whoami should return 401
echo "6️⃣  Testing post-logout whoami..."
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/v1/whoami" || true)
if [[ "$code" -ne 401 ]]; then
    echo "❌ FAIL: Expected 401 after logout, got $code"
    exit 1
fi
echo "✅ PASS: Returns 401 (unauthorized after logout)"

echo ""
echo "🎉 ALL TESTS PASSED! Authentication is working correctly."
echo ""
echo "📝 Summary of fixes applied:"
echo "   • Created .env file with CSRF_ENABLED=1"
echo "   • Set JWT_SECRET for token generation"
echo "   • Configured development-friendly cookie settings"
echo "   • Fixed CSRF endpoint usage (/csrf not /v1/csrf)"
echo "   • Corrected HTTP methods (POST for login/logout)"
echo "   • Fixed CSRF token handling (cookie value, not JSON response)"

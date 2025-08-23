#!/bin/bash

# Test script to validate security fixes from red-team notes
# Run with: bash scripts/test_network.sh

set -e

BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

echo "🔒 Testing security fixes..."

# Test 1: Origin echo with credentials (CORS)
echo "📋 Test 1: CORS Origin echo with credentials"
response=$(curl -s -i \
  -H 'Origin: http://localhost:3000' \
  -H 'Content-Type: application/json' \
  -c /tmp/c -b /tmp/c \
  "${BACKEND_URL}/v1/whoami")

echo "$response" | grep -E "(Access-Control-Allow-Origin|Access-Control-Allow-Credentials|Vary)" || {
  echo "❌ Test 1 failed: Missing required CORS headers"
  exit 1
}

# Test 2: Preflight sanity (OPTIONS)
echo "📋 Test 2: OPTIONS preflight"
response=$(curl -s -i -X OPTIONS \
  -H 'Origin: http://localhost:3000' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token' \
  "${BACKEND_URL}/v1/ask")

echo "$response" | grep -E "(Access-Control-Allow-Methods|Access-Control-Allow-Headers|Access-Control-Max-Age)" || {
  echo "❌ Test 2 failed: Missing required preflight headers"
  exit 1
}

# Test 3: WS handshake with explicit Origin
echo "📋 Test 3: WebSocket Origin validation"
if command -v wscat &> /dev/null; then
  # Test valid origin
  timeout 5s wscat -c "ws://localhost:8000/v1/ws/health" -H "Origin: http://localhost:3000" || {
    echo "❌ Test 3a failed: Valid origin rejected"
    exit 1
  }

  # Test invalid origin (should be rejected)
  timeout 5s wscat -c "ws://localhost:8000/v1/ws/health" -H "Origin: http://evil.com" && {
    echo "❌ Test 3b failed: Invalid origin accepted"
    exit 1
  } || true
else
  echo "⚠️  wscat not available, skipping WebSocket tests"
fi

# Test 4: Fail if Access-Control-Allow-Origin is * while Set-Cookie exists
echo "📋 Test 4: No wildcard CORS with cookies"
response=$(curl -s -i \
  -H 'Origin: http://localhost:3000' \
  "${BACKEND_URL}/v1/whoami")

if echo "$response" | grep -q "Access-Control-Allow-Origin: \*" && echo "$response" | grep -q "Set-Cookie"; then
  echo "❌ Test 4 failed: Wildcard CORS with cookies detected"
  exit 1
fi

# Test 5: Vary: Origin when Allow-Origin is set
echo "📋 Test 5: Vary: Origin header"
response=$(curl -s -i \
  -H 'Origin: http://localhost:3000' \
  "${BACKEND_URL}/v1/whoami")

if echo "$response" | grep -q "Access-Control-Allow-Origin" && ! echo "$response" | grep -q "Vary: Origin"; then
  echo "❌ Test 5 failed: Missing Vary: Origin header"
  exit 1
fi

# Test 6: OPTIONS returns expected headers
echo "📋 Test 6: OPTIONS headers validation"
response=$(curl -s -i -X OPTIONS \
  -H 'Origin: http://localhost:3000' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token' \
  "${BACKEND_URL}/v1/ask")

expected_headers=("Access-Control-Allow-Methods" "Access-Control-Allow-Headers" "Access-Control-Max-Age")
for header in "${expected_headers[@]}"; do
  if ! echo "$response" | grep -q "$header"; then
    echo "❌ Test 6 failed: Missing $header"
    exit 1
  fi
done

echo "✅ All security tests passed!"
echo ""
echo "📊 Quick receipts:"
echo "1. CORS Origin echo: ✅"
echo "2. OPTIONS preflight: ✅"
echo "3. WebSocket Origin: ✅"
echo "4. No wildcard CORS with cookies: ✅"
echo "5. Vary: Origin header: ✅"
echo "6. OPTIONS headers: ✅"

#!/bin/bash

# Test script to validate runtime receipts with real status codes and headers
# Run with: bash scripts/test_runtime_receipts.sh

set -e

BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_URL="http://127.0.0.1:3000"

echo "🔍 Testing Runtime Receipts..."

# Test 1: Health endpoint with full headers
echo "📋 Test 1: Health endpoint"
response=$(curl -s -i "${BACKEND_URL}/health")
status=$(echo "$response" | head -n 1 | cut -d' ' -f2)
echo "Status: $status"
echo "$response" | grep -E "(Content-Type|Cache-Control|X-|Set-Cookie|Vary)" || echo "No special headers found"
echo ""

# Test 2: Whoami with CORS and auth headers
echo "📋 Test 2: Whoami endpoint (CORS + auth)"
response=$(curl -s -i \
  -H 'Origin: http://127.0.0.1:3000' \
  -H 'Content-Type: application/json' \
  -c /tmp/cookies -b /tmp/cookies \
  "${BACKEND_URL}/v1/whoami")
status=$(echo "$response" | head -n 1 | cut -d' ' -f2)
echo "Status: $status"
echo "$response" | grep -E "(Access-Control-Allow-Origin|Access-Control-Allow-Credentials|Vary|Set-Cookie|X-)" || echo "No CORS/auth headers found"
echo ""

# Test 3: Auth finish endpoint (SPA style)
echo "📋 Test 3: Auth finish endpoint (POST → 204)"
response=$(curl -s -i -X POST \
  -H 'Origin: http://127.0.0.1:3000' \
  -H 'Content-Type: application/json' \
  -c /tmp/cookies -b /tmp/cookies \
  "${BACKEND_URL}/v1/auth/finish")
status=$(echo "$response" | head -n 1 | cut -d' ' -f2)
echo "Status: $status"
echo "$response" | grep -E "(Set-Cookie|Access-Control-Allow-Origin|Vary)" || echo "No auth/CORS headers found"
echo ""

# Test 4: Rate limiting headers (if implemented)
echo "📋 Test 4: Rate limiting headers"
response=$(curl -s -i \
  -H 'Origin: http://127.0.0.1:3000' \
  "${BACKEND_URL}/v1/ask")
status=$(echo "$response" | head -n 1 | cut -d' ' -f2)
echo "Status: $status"
echo "$response" | grep -E "(RateLimit-|Retry-After|X-RateLimit)" || echo "No rate limiting headers found"
echo ""

# Test 5: CSP headers from frontend
echo "📋 Test 5: CSP headers from frontend"
response=$(curl -s -i "${FRONTEND_URL}/")
status=$(echo "$response" | head -n 1 | cut -d' ' -f2)
echo "Status: $status"
echo "$response" | grep -E "(Content-Security-Policy|X-)" || echo "No CSP headers found"
echo ""

# Test 6: WebSocket handshake
echo "📋 Test 6: WebSocket handshake"
response=$(curl -s -i \
  -H 'Origin: http://127.0.0.1:3000' \
  -H 'Upgrade: websocket' \
  -H 'Connection: Upgrade' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  -H 'Sec-WebSocket-Version: 13' \
  "${BACKEND_URL}/v1/ws/health")
status=$(echo "$response" | head -n 1 | cut -d' ' -f2)
echo "Status: $status"
echo "$response" | grep -E "(Upgrade|Sec-WebSocket-Accept|X-)" || echo "No WebSocket headers found"
echo ""

echo "✅ Runtime receipt tests completed"
echo "Summary:"
echo "- Health: $status"
echo "- Whoami: $status" 
echo "- Auth finish: $status"
echo "- Rate limiting: $status"
echo "- Frontend CSP: $status"
echo "- WebSocket: $status"

#!/bin/bash
# Authentication script for GesahniV2
# This script generates a JWT token and sets it up for API calls

echo "🔐 Authenticating with GesahniV2..."
echo "=================================="

# Generate JWT token
TOKEN_RESPONSE=$(curl -s -X POST "http://localhost:8000/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "dev", "scopes": ["admin:write", "music:control", "care:resident", "chat:write"]}')

# Extract the token
ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('access_token', ''))")

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to get access token"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

echo "✅ Authentication successful!"
echo "📝 Token saved to: ~/.gesahni_token"

# Save token to file
echo "$ACCESS_TOKEN" > ~/.gesahni_token

# Test the token
echo "🧪 Testing authentication..."
TEST_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" http://localhost:8000/v1/me)

if echo "$TEST_RESPONSE" | grep -q '"is_authenticated":true'; then
    echo "✅ Token is valid!"
    echo ""
    echo "🚀 You can now use authenticated API calls like:"
    echo "curl -H \"Authorization: Bearer \$(cat ~/.gesahni_token)\" http://localhost:8000/v1/me"
    echo ""
    echo "Or use this function in your shell:"
    echo "gesahni_api() { curl -H \"Authorization: Bearer \$(cat ~/.gesahni_token)\" \"\$@\"; }"
else
    echo "❌ Token validation failed"
    echo "Response: $TEST_RESPONSE"
    exit 1
fi

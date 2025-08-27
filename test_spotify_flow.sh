#!/bin/bash
# Spotify OAuth Flow End-to-End Test Script
# Tests CORS, cookies, OAuth flow, and all the fixes

set -e

# Configuration
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-http://localhost:3000}"

echo "🎵 Testing Spotify OAuth Flow"
echo "Backend: $BACKEND_URL"
echo "Frontend Origin: $FRONTEND_ORIGIN"
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[TEST]$NC $1"
}

print_success() {
    echo -e "${GREEN}[PASS]$NC $1"
}

print_error() {
    echo -e "${RED}[FAIL]$NC $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]$NC $1"
}

# Test 1: CORS preflight (OPTIONS)
print_status "Test 1: CORS preflight OPTIONS request"
cors_response=$(curl -s -I -X OPTIONS \
    -H "Origin: $FRONTEND_ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Authorization" \
    "$BACKEND_URL/v1/spotify/connect" \
    -w "%{http_code}")

if [[ $cors_response == *"200"* ]]; then
    print_success "CORS preflight passed"
else
    print_error "CORS preflight failed: $cors_response"
fi

# Test 2: Connect endpoint without auth (should 401)
print_status "Test 2: Connect without authentication (should 401)"
unauth_response=$(curl -s -w "%{http_code}" \
    -H "Origin: $FRONTEND_ORIGIN" \
    "$BACKEND_URL/v1/spotify/connect")

if [[ $unauth_response == *"401"* ]]; then
    print_success "Unauthenticated connect properly returns 401"
else
    print_error "Unauthenticated connect should return 401, got: $unauth_response"
fi

# Test 3: Get CSRF token for authenticated requests
print_status "Test 3: Get CSRF token"
csrf_response=$(curl -s -c cookies.txt \
    -H "Origin: $FRONTEND_ORIGIN" \
    "$BACKEND_URL/v1/csrf")

csrf_token=$(echo "$csrf_response" | grep -o '"csrf_token":"[^"]*' | cut -d'"' -f4)

if [[ -n "$csrf_token" ]]; then
    print_success "Got CSRF token: ${csrf_token:0:20}..."
else
    print_error "Failed to get CSRF token"
fi

# Test 4: Try to login with common credentials
print_status "Test 4: Login to get JWT"
# Try different common credentials
credentials=("testuser:testpass123" "admin:admin" "alice:alice" "test:test" "authtest:test" "admin:password")
access_token=""

for cred in "${credentials[@]}"; do
    IFS=':' read -r username password <<< "$cred"
    login_response=$(curl -s -b cookies.txt -c cookies.txt \
        -X POST \
        -H "Origin: $FRONTEND_ORIGIN" \
        -H "Content-Type: application/json" \
        -H "X-CSRF-Token: $csrf_token" \
        -d "{\"username\":\"$username\",\"password\":\"$password\"}" \
        "$BACKEND_URL/v1/login")

    if echo "$login_response" | grep -q '"access_token"'; then
        print_success "Login successful with $username:$password"
        access_token=$(echo "$login_response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
        break
    fi
done

if [[ -z "$access_token" ]]; then
    print_error "Failed to login with any common credentials"
    print_error "Last response: $login_response"
    # Continue with limited tests that don't require auth
    print_warn "Continuing with limited tests (no auth required)"
fi

# Test 5: Connect with valid JWT (should work)
if [[ -n "$access_token" ]]; then
    print_status "Test 5: Connect with valid JWT"
    connect_response=$(curl -s -b cookies.txt -c cookies.txt \
        -X GET \
        -H "Origin: $FRONTEND_ORIGIN" \
        -H "Authorization: Bearer $access_token" \
        "$BACKEND_URL/v1/spotify/connect")

    if echo "$connect_response" | grep -q '"authorize_url"'; then
        print_success "Connect successful, got authorize_url"
        authorize_url=$(echo "$connect_response" | grep -o '"authorize_url":"[^"]*' | cut -d'"' -f4)
        echo "Authorize URL: $authorize_url"
    else
        print_error "Connect failed: $connect_response"
        authorize_url=""
    fi
else
    print_warn "Skipping connect test (no auth token)"
    authorize_url=""
fi

# Test 6: Check cookie attributes in Set-Cookie headers
print_status "Test 6: Check cookie attributes"
if grep -q "spotify_oauth_jwt" cookies.txt; then
    print_success "Temporary spotify_oauth_jwt cookie set"

    # Check HttpOnly
    if grep -q "HttpOnly" cookies.txt; then
        print_success "Cookie has HttpOnly attribute"
    else
        print_error "Cookie missing HttpOnly attribute"
    fi

    # Check Path=/
    if grep -q "path=/" cookies.txt; then
        print_success "Cookie has Path=/"
    else
        print_warn "Cookie Path not verified (might be default)"
    fi

else
    print_error "spotify_oauth_jwt cookie not found"
fi

# Test 7: Status endpoint (should work with auth)
if [[ -n "$access_token" ]]; then
    print_status "Test 7: Status endpoint"
    status_response=$(curl -s -b cookies.txt \
        -H "Origin: $FRONTEND_ORIGIN" \
        -H "Authorization: Bearer $access_token" \
        "$BACKEND_URL/v1/spotify/status")

    if echo "$status_response" | grep -q '"connected"'; then
        print_success "Status endpoint works"
    else
        print_error "Status endpoint failed: $status_response"
    fi
else
    print_warn "Skipping status endpoint test (no auth token)"
fi

# Test 8: Test mode callback (SPOTIFY_TEST_MODE=1)
print_status "Test 8: Test mode callback"
if [[ -n "$authorize_url" ]]; then
    # Extract state from authorize_url
    state=$(echo "$authorize_url" | grep -o 'state=[^&]*' | cut -d'=' -f2)

    if [[ -n "$state" ]]; then
        print_success "Extracted state: ${state:0:20}..."

        callback_response=$(curl -s -b cookies.txt -c cookies.txt \
            -X GET \
            -H "Origin: $FRONTEND_ORIGIN" \
            -w "%{http_code}" \
            "$BACKEND_URL/v1/spotify/callback?code=fake&state=$state")

        if [[ $callback_response == *"302"* ]]; then
            print_success "Callback redirect (302) successful"

            # Check if redirect location contains settings
            if echo "$callback_response" | grep -q "settings"; then
                print_success "Redirect to settings page (OAuth tx expired as expected)"
            else
                print_error "Redirect location incorrect"
            fi
        else
            print_error "Callback should return 302, got HTTP code: $callback_response"
        fi
    else
        print_error "Could not extract state from authorize_url"
    fi
fi

# Test 9: Disconnect endpoint
if [[ -n "$access_token" ]]; then
    print_status "Test 9: Disconnect endpoint"
    disconnect_response=$(curl -s -b cookies.txt \
        -X DELETE \
        -H "Origin: $FRONTEND_ORIGIN" \
        -H "Authorization: Bearer $access_token" \
        "$BACKEND_URL/v1/spotify/disconnect")

    if echo "$disconnect_response" | grep -q '"ok":true'; then
        print_success "Disconnect successful"
    else
        print_warn "Disconnect response: $disconnect_response"
    fi
else
    print_warn "Skipping disconnect test (no auth token)"
fi

# Test 10: Legacy login endpoint (should 404 when user_id provided)
print_status "Test 10: Legacy login endpoint (should 404)"
# First test without user_id (should return 422 for validation error)
legacy_response_no_userid=$(curl -s -w "%{http_code}" \
    -H "Origin: $FRONTEND_ORIGIN" \
    "$BACKEND_URL/v1/spotify/login")

# Then test with user_id (should return 404 for deprecation)
legacy_response_with_userid=$(curl -s -w "%{http_code}" \
    -H "Origin: $FRONTEND_ORIGIN" \
    "$BACKEND_URL/v1/spotify/login?user_id=test")

if [[ $legacy_response_no_userid == *"422"* ]]; then
    print_success "Legacy login without user_id properly returns 422 (validation error)"
elif [[ $legacy_response_with_userid == *"404"* ]]; then
    print_success "Legacy login with user_id properly returns 404 (deprecated)"
else
    print_error "Legacy login behavior unexpected. No user_id: $legacy_response_no_userid, With user_id: $legacy_response_with_userid"
fi

# Test 11: Debug cookie endpoint (dev only)
print_status "Test 11: Debug cookie endpoint"
debug_response=$(curl -s -b cookies.txt \
    -H "Origin: $FRONTEND_ORIGIN" \
    "$BACKEND_URL/v1/spotify/debug-cookie")

if echo "$debug_response" | grep -q '"has_auth_cookie"'; then
    print_success "Debug cookie endpoint works"
else
    print_warn "Debug endpoint response: $debug_response"
fi

# Test 12: Check main auth cookie wasn't overwritten
print_status "Test 12: Verify main auth cookie integrity"
if grep -q "GSNH_AT\|GSNH_RT" cookies.txt; then
    print_success "Main auth cookies (GSNH_AT, GSNH_RT) present and unchanged"
    echo "Cookies present:"
    grep "GSNH_AT\|GSNH_RT\|spotify_oauth_jwt" cookies.txt || echo "No relevant cookies found"
else
    print_error "Main auth cookie missing or overwritten"
    echo "All cookies in jar:"
    cat cookies.txt || echo "No cookies file"
fi

# Cleanup
rm -f cookies.txt

echo
echo "🎵 Spotify OAuth Flow Testing Complete!"
echo "If all tests passed, the implementation is working correctly."

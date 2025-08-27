#!/bin/bash

# 🔐 AUTH DEBUGGING SCRIPT
# Test cookie-based authentication flow
# This proves cookies exist and travel between requests

echo "🔐 AUTH COOKIE DEBUGGING"
echo "========================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_BASE="http://localhost:8000"
COOKIE_FILE="/tmp/gsnh_cookies.txt"

echo -e "${BLUE}Step 1: Testing POST /v1/refresh${NC}"
echo "This should create new cookies if authentication works"
echo ""

# Clean up any existing cookie file
rm -f "$COOKIE_FILE"

# 1) Try to login first to get tokens, then test refresh
echo "Command: curl -i -s -X POST $API_BASE/v1/login -H 'Content-Type: application/json' -c $COOKIE_FILE -b $COOKIE_FILE -d '{\"username\":\"test\",\"password\":\"test\"}'"
echo ""

LOGIN_RESPONSE=$(curl -i -s -X POST "$API_BASE/v1/login" \
  -H 'Content-Type: application/json' \
  -c "$COOKIE_FILE" \
  -b "$COOKIE_FILE" \
  -d '{"username":"test","password":"test"}')

echo "$LOGIN_RESPONSE"
echo ""

# Extract status code
LOGIN_STATUS=$(echo "$LOGIN_RESPONSE" | grep -o "HTTP/[0-9.]* [0-9]*" | tail -1 | awk '{print $2}')

if [ "$LOGIN_STATUS" = "200" ]; then
    echo -e "${GREEN}✅ Login endpoint returned 200 OK${NC}"
    echo "Now testing refresh with the obtained tokens..."
    echo ""

    # 1) Hit refresh and capture cookies (using existing cookies from login)
    echo "Command: curl -i -s -X POST $API_BASE/v1/refresh -H 'Content-Type: application/json' -c $COOKIE_FILE -b $COOKIE_FILE -d '{}'"
    echo ""

    RESPONSE=$(curl -i -s -X POST "$API_BASE/v1/refresh" \
      -H 'Content-Type: application/json' \
      -c "$COOKIE_FILE" \
      -b "$COOKIE_FILE" \
      -d '{}')
else
    echo -e "${RED}❌ Login endpoint failed with status $LOGIN_STATUS${NC}"
    echo "Trying refresh without login (may fail)..."
    echo ""

    # 1) Hit refresh and capture cookies (may fail without login)
    echo "Command: curl -i -s -X POST $API_BASE/v1/refresh -H 'Content-Type: application/json' -c $COOKIE_FILE -b $COOKIE_FILE -d '{}'"
    echo ""

    RESPONSE=$(curl -i -s -X POST "$API_BASE/v1/refresh" \
      -H 'Content-Type: application/json' \
      -c "$COOKIE_FILE" \
      -b "$COOKIE_FILE" \
      -d '{}')
fi

echo "$RESPONSE"
echo ""

# Check if cookies were created
if [ -f "$COOKIE_FILE" ] && [ -s "$COOKIE_FILE" ]; then
    echo -e "${GREEN}✅ Cookies file created! Contents:${NC}"
    cat "$COOKIE_FILE"
    echo ""
else
    echo -e "${RED}❌ No cookies were created!${NC}"
    echo ""
fi

# Extract status code
STATUS_CODE=$(echo "$RESPONSE" | grep -o "HTTP/[0-9.]* [0-9]*" | tail -1 | awk '{print $2}')

if [ "$STATUS_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Refresh endpoint returned 200 OK${NC}"
else
    echo -e "${RED}❌ Refresh endpoint failed with status $STATUS_CODE${NC}"
fi

echo ""
echo "========================================="
echo ""

echo -e "${BLUE}Step 2: Testing GET /v1/whoami with cookies${NC}"
echo "This should use the cookies from step 1 to authenticate"
echo ""

# 2) Call whoami with those cookies
echo "Command: curl -i -s $API_BASE/v1/whoami -c $COOKIE_FILE -b $COOKIE_FILE"
echo ""

WHOAMI_RESPONSE=$(curl -i -s "$API_BASE/v1/whoami" \
  -c "$COOKIE_FILE" \
  -b "$COOKIE_FILE")

echo "$WHOAMI_RESPONSE"
echo ""

# Extract whoami status code
WHOAMI_STATUS=$(echo "$WHOAMI_RESPONSE" | grep -o "HTTP/[0-9.]* [0-9]*" | tail -1 | awk '{print $2}')

if [ "$WHOAMI_STATUS" = "200" ]; then
    echo -e "${GREEN}✅ Whoami endpoint returned 200 OK${NC}"
    echo -e "${GREEN}✅ Cookies are working correctly!${NC}"

    # Try to extract user info from response
    USER_INFO=$(echo "$WHOAMI_RESPONSE" | sed -n '/{/,/}/p' | jq -r '.user_id // empty' 2>/dev/null)
    if [ ! -z "$USER_INFO" ]; then
        echo -e "${GREEN}✅ Authenticated as user: $USER_INFO${NC}"
    fi
else
    echo -e "${RED}❌ Whoami endpoint failed with status $WHOAMI_STATUS${NC}"
    echo -e "${RED}❌ Cookie authentication is NOT working${NC}"
    echo ""
    echo -e "${YELLOW}Possible issues:${NC}"
    echo "  - Cookies not being set properly by refresh endpoint"
    echo "  - Cookie attributes (SameSite, Secure, etc.) are misconfigured"
    echo "  - Cookie domain/path mismatch"
    echo "  - Server not reading cookies correctly"
fi

echo ""
echo "========================================="
echo ""

# Show current cookies for debugging
if [ -f "$COOKIE_FILE" ] && [ -s "$COOKIE_FILE" ]; then
    echo -e "${BLUE}Current cookies in file:${NC}"
    cat "$COOKIE_FILE"
    echo ""

    COOKIE_COUNT=$(wc -l < "$COOKIE_FILE")
    echo -e "${BLUE}Total cookies: $COOKIE_COUNT${NC}"
else
    echo -e "${RED}No cookie file or empty cookie file${NC}"
fi

echo ""
echo "========================================="
echo ""

if [ "$STATUS_CODE" = "200" ] && [ "$WHOAMI_STATUS" = "200" ]; then
    echo -e "${GREEN}🎉 SUCCESS: Cookie-based authentication is working!${NC}"
    echo "The authentication flow is functioning correctly."
else
    echo -e "${RED}❌ FAILURE: Cookie authentication is broken${NC}"
    echo "Check the issues listed above and fix your cookie configuration."
fi

echo ""
echo -e "${YELLOW}Cleanup: Removing temporary cookie file${NC}"
rm -f "$COOKIE_FILE"
echo -e "${YELLOW}Done.${NC}"

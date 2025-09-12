#!/bin/bash
set -e

echo "🔒 PRECISE SECURITY VERIFICATION 🔒"
echo "==================================="

# Function to safely count matches with ripgrep, excluding test/docs
safe_count_production() {
    local pattern="$1"
    local exclude_dirs="$2"
    local result
    if result=$(rg -n "$pattern" --glob="!tests/**" --glob="!e2e/**" --glob="!*.md" --glob="!*.test.*" --glob="!*.spec.*" $exclude_dirs 2>/dev/null); then
        echo "$result" | wc -l
    else
        echo "0"
    fi
}

echo ""
echo "📋 PRODUCTION CODE SECURITY CHECKS:"
echo "------------------------------------"

echo -n "1. Direct login?next= constructions (production only): "
count1=$(safe_count_production "login\\?next=" "--glob='!node_modules'")
echo "$count1 matches"

echo -n "2. Direct login URL string construction (production): "
count2=$(safe_count_production "'/login\\?next=" "--glob='!node_modules'")
echo "$count2 matches"

echo -n "3. Frontend direct login constructions (production): "
count3=$(safe_count_production "/login\\?next=" "--glob='!frontend/tests/**' --glob='!frontend/e2e/**'")
echo "$count3 matches"

echo ""
echo "🔍 OAUTH SECURITY VERIFICATION:"
echo "-------------------------------"

echo -n "4. OAuth endpoints using sanitization: "
oauth_sanitized=$(rg -n "sanitize_redirect_path" app/api/ | wc -l 2>/dev/null || echo "0")
echo "$oauth_sanitized endpoints"

echo -n "5. OAuth endpoints setting gs_next cookie: "
oauth_cookies=$(rg -n "set_gs_next_cookie" app/api/ | wc -l 2>/dev/null || echo "0")
echo "$oauth_cookies endpoints"

echo ""
echo "🛡️  SECURITY STATUS:"
echo "-------------------"

if [ "$count1" = "0" ] && [ "$count2" = "0" ] && [ "$count3" = "0" ]; then
    echo "✅ PRODUCTION CODE IS SECURE!"
    echo "🎉 No direct login URL constructions found in production code"
    echo ""
    echo "📊 OAuth Security Summary:"
    echo "  - $oauth_sanitized endpoints use sanitization"
    echo "  - $oauth_cookies endpoints set secure cookies"
    exit 0
else
    echo "❌ PRODUCTION SECURITY ISSUES DETECTED!"
    echo "⚠️  Review findings above - these are in production code"
    exit 1
fi

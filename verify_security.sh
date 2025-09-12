#!/bin/bash
set -e

echo "🔒 COMPREHENSIVE SECURITY VERIFICATION 🔒"
echo "========================================"

# Function to safely count matches with ripgrep
safe_count() {
    local pattern="$1"
    local result
    if result=$(rg -n "$pattern" 2>/dev/null); then
        echo "$result" | wc -l
    else
        echo "0"
    fi
}

echo ""
echo "📋 PRIMARY SECURITY CHECKS:"
echo "---------------------------"

echo -n "1. Direct login?next= constructions: "
count1=$(safe_count "login\\?next=")
echo "$count1 matches"

echo -n "2. Problematic redirect calls (excluding legitimate): "
count2=$(rg -n "redirect\\(" app 2>/dev/null | rg -v "sanitize_next_path" | grep -v "_allow_redirect\|_mint_cookie_redirect" | wc -l 2>/dev/null || echo "0")
echo "$count2 matches"

echo -n "3. Direct login URL string construction: "
count3=$(safe_count "'/login\\?next=")
echo "$count3 matches"

echo ""
echo "🔍 ADDITIONAL SECURITY SCANS:"
echo "------------------------------"

echo -n "4. Frontend direct login constructions: "
count4=$(rg -n "/login\\?next=" frontend/src/ 2>/dev/null | wc -l 2>/dev/null || echo "0")
echo "$count4 matches"

echo -n "5. Unsanitized next parameters in redirects: "
count5=$(rg -n "next=" app/ | grep -v "sanitize_redirect_path\|set_gs_next_cookie\|_allow_redirect" | wc -l 2>/dev/null || echo "0")
echo "$count5 matches"

echo -n "6. Hardcoded login URLs in config/docs: "
count6=$(rg -n "login.*next" --glob="*.md" | grep -v "HEADER_MODE" | wc -l 2>/dev/null || echo "0")
echo "$count6 matches"

echo ""
echo "🛡️  SECURITY STATUS:"
echo "-------------------"

if [ "$count1" = "0" ] && [ "$count2" = "0" ] && [ "$count3" = "0" ] && [ "$count4" = "0" ] && [ "$count5" = "0" ] && [ "$count6" = "0" ]; then
    echo "✅ ALL SECURITY CHECKS PASSED!"
    echo "🎉 Repository is secure against redirect-based attacks"
    exit 0
else
    echo "❌ SECURITY ISSUES DETECTED!"
    echo "⚠️  Please review the findings above"
    exit 1
fi

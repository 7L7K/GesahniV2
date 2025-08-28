#!/bin/bash
# GesahniV2 Security Smoke Check Script
# Finds remaining URL previews/state leaks, direct sqlite use in async routes, and bad DI patterns

set -e

echo "🔍 GesahniV2 Security Smoke Check"
echo "================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    if [ "$status" -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $message"
    else
        echo -e "${RED}✗${NC} $message"
    fi
}

# Function to run grep and check results
check_pattern() {
    local pattern="$1"
    local description="$2"
    local exclude_pattern="$3"

    echo ""
    echo "Checking: $description"
    echo "Pattern: $pattern"

    if [ -n "$exclude_pattern" ]; then
        result=$(grep -rn "$pattern" app | grep -v "$exclude_pattern" || true)
    else
        result=$(grep -rn "$pattern" app || true)
    fi

    if [ -z "$result" ]; then
        print_status 0 "No matches found"
    else
        print_status 1 "Found matches:"
        echo "$result"
        echo ""
    fi
}

# 1. Find any remaining URL previews/state leaks
echo ""
echo "1️⃣ Finding URL previews/state leaks..."
echo "======================================"

check_pattern "state_preview|auth_url_preview|auth_url_prefix|authorize_url.*log" "URL previews/state leaks in logs"

# 2. Find any direct sqlite use in async routes
echo ""
echo "2️⃣ Finding direct sqlite use in async routes..."
echo "=============================================="

# First find async routes
echo "Finding async routes with sqlite3.connect:"
async_sqlite_routes=$(grep -rn "sqlite3\.connect" app | grep -E "@router\.(get|post|delete|put|patch)" || true)

if [ -z "$async_sqlite_routes" ]; then
    print_status 0 "No direct sqlite use in async routes"
else
    print_status 1 "Found direct sqlite use in async routes:"
    echo "$async_sqlite_routes"
    echo ""
fi

# 3. Find bad DI patterns
echo ""
echo "3️⃣ Finding bad DI patterns..."
echo "=============================="

check_pattern ":\s*[^=]+=\s*get_current_user_id(?!\s*\))" "Bad DI patterns (get_current_user_id not in function call)"

# Additional security checks
echo ""
echo "4️⃣ Additional security checks..."
echo "=================================="

# Find potential logging of sensitive data
echo "Checking for potential sensitive data logging:"
sensitive_patterns=(
    "password.*log|log.*password"
    "token.*log|log.*token"
    "secret.*log|log.*secret"
    "key.*log|log.*key"
    "jwt.*log|log.*jwt"
    "state.*log|log.*state"
    "code.*log|log.*code"
)

for pattern in "${sensitive_patterns[@]}"; do
    check_pattern "$pattern" "Potential sensitive data in logs" "test_|_test\.py"
done

# Find missing error handling
echo ""
echo "Checking for missing error handling in OAuth flows:"
oauth_error_patterns=(
    "except.*:\s*pass"
    "except Exception:\s*pass"
)

for pattern in "${oauth_error_patterns[@]}"; do
    check_pattern "$pattern" "Bare except clauses" "test_|_test\.py"
done

# Check for hardcoded secrets
echo ""
echo "Checking for hardcoded secrets:"
secret_patterns=(
    "password\s*=\s*['\"][^'\"]*['\"]"
    "secret\s*=\s*['\"][^'\"]*['\"]"
    "token\s*=\s*['\"][^'\"]*['\"]"
    "key\s*=\s*['\"][^'\"]*['\"]"
)

for pattern in "${secret_patterns[@]}"; do
    check_pattern "$pattern" "Potential hardcoded secrets" "test_|_test\.py|_example\.py|example_|conftest\.py"
done

# Check cookie settings consistency
echo ""
echo "Checking cookie settings consistency:"
cookie_patterns=(
    "set_cookie.*secure.*false|secure.*False"
    "set_cookie.*httponly.*false|httponly.*False"
    "SameSite.*none|SameSite.*None"
)

for pattern in "${cookie_patterns[@]}"; do
    check_pattern "$pattern" "Cookie security settings" "test_|_test\.py"
done

# Summary
echo ""
echo "🎯 Security Smoke Check Complete"
echo "================================"
echo ""
echo "Summary of checks performed:"
echo "• URL previews/state leaks in logs"
echo "• Direct sqlite use in async routes"
echo "• Bad DI patterns"
echo "• Potential sensitive data logging"
echo "• Bare except clauses"
echo "• Hardcoded secrets"
echo "• Cookie security settings"
echo ""
echo "Review any items marked with ✗ above and address as needed."
echo ""

# Exit with success
exit 0

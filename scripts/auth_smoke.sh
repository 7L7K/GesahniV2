#!/usr/bin/env bash
set -euo pipefail
API=${API:-http://localhost:8000}

echo "Step 1: Getting CSRF token..."
curl -s -i -c /tmp/c.jar -b /tmp/c.jar $API/v1/csrf | tee /tmp/csrf.txt >/dev/null
echo "CSRF response:"
cat /tmp/csrf.txt
echo ""

echo "Step 2: Checking CSRF cookie..."
grep -qi 'Set-Cookie:.*csrf_token' /tmp/csrf.txt && echo "✅ CSRF token found in Set-Cookie" || echo "❌ CSRF token NOT found in Set-Cookie"
! grep -qi 'Set-Cookie:.*Secure' /tmp/csrf.txt && echo "✅ CSRF not Secure" || echo "❌ CSRF is Secure"
! grep -qi 'Set-Cookie:.*HttpOnly' /tmp/csrf.txt && echo "✅ CSRF not HttpOnly" || echo "❌ CSRF is HttpOnly"
echo ""

echo "Step 3: Extracting CSRF token..."
CSRF=$(grep csrf_token /tmp/c.jar | awk '{print $7}')
echo "Extracted CSRF: $CSRF"
echo ""

echo "Step 4: Refreshing tokens..."
curl -s -i -c /tmp/c.jar -b /tmp/c.jar -H "x-csrf-token: $CSRF" -X POST $API/v1/auth/refresh \
  | tee /tmp/refresh.txt >/dev/null
echo "Refresh response:"
cat /tmp/refresh.txt
echo ""

echo "Step 5: Checking refresh cookies..."
grep -Eqi 'Set-Cookie:.*(GSNH_AT|access_token)=' /tmp/refresh.txt && echo "✅ Access token found in Set-Cookie" || echo "❌ Access token NOT found in Set-Cookie"
echo ""

echo "Step 6: Testing whoami..."
curl -s -i -c /tmp/c.jar -b /tmp/c.jar $API/v1/whoami | head -n1 | grep -q "200" && echo "✅ Whoami returns 200" || echo "❌ Whoami does not return 200"
echo ""

echo "✅ auth smoke passed"

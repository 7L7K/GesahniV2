#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

note() { echo -e "\n==> $*"; }

curl_json() {
  local method="$1"; shift
  local url="$1"; shift
  curl -sS -X "$method" -H 'Accept: application/json' -H 'Content-Type: application/json' -c cookies.txt -b cookies.txt "$url" "$@"
}

note "CSRF public endpoint"
curl_json GET "$BASE_URL/v1/auth/csrf" | jq . || true

note "Pre-auth whoami should be 401"
code=$(curl -s -o /dev/null -w "%{http_code}" -b cookies.txt "$BASE_URL/v1/whoami")
echo "HTTP $code"

note "Login with demo creds (if enabled)"
resp=$(curl -sS -X POST -H 'Content-Type: application/json' -c cookies.txt -b cookies.txt \
  "$BASE_URL/v1/auth/login" \
  --data '{"username":"demo","password":"demo"}')
echo "$resp"

note "Post-login whoami should be 200"
code=$(curl -s -o /dev/null -w "%{http_code}" -b cookies.txt "$BASE_URL/v1/whoami")
echo "HTTP $code"

note "Logout"
curl -sS -X POST -c cookies.txt -b cookies.txt "$BASE_URL/v1/auth/logout" -o /dev/null || true

note "After logout whoami should be 401"
code=$(curl -s -o /dev/null -w "%{http_code}" -b cookies.txt "$BASE_URL/v1/whoami")
echo "HTTP $code"

echo -e "\nDone."

#!/usr/bin/env bash
set -euo pipefail

# Dev auth probe: /v1/csrf -> /v1/auth/login -> /v1/whoami
# Use FRONTEND origin when proxying (same-origin dev).
BASE_URL="${BASE_URL:-http://localhost:3000}"
JAR="$(mktemp -t dev_auth_jar.XXXXXX)"
HDRS="$(mktemp -t dev_auth_hdrs.XXXXXX)"
trap 'rm -f "$JAR" "$HDRS"' EXIT

echo "[i] Using BASE_URL=${BASE_URL}"

echo "[1/3] GET /v1/csrf"
csrf_json="$(curl -sS -i -c "$JAR" -H 'Accept: application/json' "$BASE_URL/v1/csrf")"
echo "$csrf_json" | grep -i '^Set-Cookie:' || true
CSRF_TOKEN="$(echo "$csrf_json" | sed -n '/^{/,/^}/p' | sed -n 's/.*"csrf_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
if [ -z "${CSRF_TOKEN:-}" ]; then
  CSRF_TOKEN="$(echo "$csrf_json" | awk 'BEGIN{IGNORECASE=1} /^X-CSRF-Token:/ {print $0}' | sed -E 's/^X-CSRF-Token:\s*//I' | tr -d '\r')"
fi
echo "[i] CSRF_TOKEN=${CSRF_TOKEN:-<missing>}"

echo "[2/3] POST /v1/auth/login?username=dev (expect Set-Cookie)"
curl -sS -D "$HDRS" -o /dev/null -b "$JAR" -c "$JAR" \
  -X POST \
  -H "X-CSRF-Token: ${CSRF_TOKEN:-}" \
  "$BASE_URL/v1/auth/login?username=dev"
echo "--- Set-Cookie headers ---"
grep -i '^Set-Cookie:' "$HDRS" || echo "(none)"
echo "--------------------------"

echo "[3/3] GET /v1/whoami"
curl -sS -b "$JAR" "$BASE_URL/v1/whoami"
echo
echo "[ok] Done."

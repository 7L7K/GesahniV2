#!/usr/bin/env bash
set -euo pipefail

# Tiny probe: login -> Set-Cookie -> whoami with cookie jar
# Usage: tools/cors_cookie_probe.sh http://localhost:8000 http://localhost:3000

API_ORIGIN=${1:-http://localhost:8000}
FRONT_ORIGIN=${2:-http://localhost:3000}

JAR=$(mktemp)
trap 'rm -f "$JAR"' EXIT

echo "==> Probing with API_ORIGIN=${API_ORIGIN} FRONT_ORIGIN=${FRONT_ORIGIN}" >&2

echo "-- Login (expect Set-Cookie)" >&2
code=$(curl -sk -X POST "${API_ORIGIN}/v1/auth/login?username=probe" \
  -H "Origin: ${FRONT_ORIGIN}" \
  -D >(tee /dev/stderr | sed -n '1,30p' >/dev/null) \
  -c "$JAR" -o /dev/null -w "%{http_code}")
echo "HTTP ${code}" >&2

echo "-- Whoami with cookie jar (credentials included)" >&2
curl -sk "${API_ORIGIN}/v1/whoami" \
  -H "Origin: ${FRONT_ORIGIN}" \
  -b "$JAR" -D -

echo "-- Cookies captured" >&2
cat "$JAR" >&2


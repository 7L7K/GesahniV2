#!/usr/bin/env bash
set -euo pipefail

base="${1:-http://localhost:8000}"
jar="$(mktemp)"
trap 'rm -f "$jar"' EXIT

say() { printf "\n— %s —\n" "$*"; }

say "Unauthed whoami"
curl -sk -D- -c "$jar" "$base/v1/auth/whoami" | sed -n '1,15p'

say "Login (test user)"
curl -sk -X POST -b "$jar" -c "$jar" "$base/v1/auth/login" \
  -H 'content-type: application/json' \
  --data '{"username":"qazwsxppo","password":"whatever"}' | jq .

say "Authed whoami"
curl -sk -b "$jar" -c "$jar" "$base/v1/auth/whoami" | jq .

say "JWT info"
curl -sk -b "$jar" "$base/v1/auth/jwt-info" | jq .

say "Spotify status"
curl -sk -b "$jar" "$base/v1/integrations/spotify/status" | jq .

say "Spotify login_url (authed)"
curl -sk -b "$jar" "$base/v1/auth/spotify/login_url" | jq .

say "Spotify login_url (anon)"
curl -sk "$base/v1/auth/spotify/login_url" | jq .

say "Google login_url"
curl -sk "$base/v1/google/login_url" | jq .
#!/usr/bin/env bash
set -euo pipefail

# Lightweight start wrapper — calls the dev orchestrator.
# Historically this script existed for the 'gesahni-start' helper.

cd "$(dirname "$0")/.."
if [ ! -f ./scripts/dev.sh ]; then
  echo "❌ ./scripts/dev.sh not found; cannot start development environment"
  exit 1
fi

echo "🚀 Launching Gesahni development environment (via ./scripts/dev.sh)"
exec ./scripts/dev.sh

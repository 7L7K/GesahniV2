#!/bin/bash
# 🧠 Gesahni Env Doctor – MacOS Edition  (auto-deactivate)

set -e

say()  { echo -e "\033[1;35m$1\033[0m"; }
warn() { echo -e "\033[1;33m$1\033[0m"; }
good() { echo -e "\033[1;32m$1\033[0m"; }
bad()  { echo -e "\033[1;31m$1\033[0m"; }

VENV_DIR=".venv"
PY_CMD="python3"

say "🔍  Python: $("$PY_CMD" --version 2>/dev/null || echo 'missing')"

IN_VENV=$("$PY_CMD" - <<'PY'
import sys, pathlib, os
print(pathlib.Path(sys.prefix).resolve().name == ".venv")
PY
)

# ───────────────── Package checks (omitted for brevity) ──────────────
# … keep your existing package-version loop here …

say "\n🔁  Reset env?"
read -r -p "   Type y to rebuild ${VENV_DIR} (will DELETE it): " CONF
[[ "$CONF" =~ ^[yY]$ ]] || { bad "🚫  Cancelled."; exit 0; }

# ── If we are *inside* the venv, step out so we can delete it cleanly
if [[ "$IN_VENV" == "True" ]]; then
  say "⏏️  Deactivating current venv before wipe…"
  deactivate
fi

# ── Blow it away & build fresh
rm -rf "$VENV_DIR"
"$PY_CMD" -m venv "$VENV_DIR"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

pip install -U pip setuptools wheel
pip install \
  numpy~=1.26 rapidfuzz~=3.6 \
  torch==2.2.2 "safetensors<0.4.3" \
  sentence-transformers==2.7.0 chromadb~=0.5 \
  pytest~=8.4 pytest-asyncio~=0.23 anyio~=4.9 \
  fastapi uvicorn python-dotenv httpx

good "\n✅  Fresh venv ready → $(which python)"
say  "   Tip: export VECTOR_STORE=memory  (tests)"
exec "$SHELL" -i          # drop you into the new env interactively

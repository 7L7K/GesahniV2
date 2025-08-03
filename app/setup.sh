# app/setup.sh
python -m venv .venv
source .venv/bin/activate
pip install --disable-pip-version-check -r requirements.txt

# Optional fast-lint tools
pip install pyright ruff || true

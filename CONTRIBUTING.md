# Contributing to GesahniV2

Thanks for your interest in contributing! This guide explains how to set up your environment, run tests, and open high‑quality pull requests.

## Prerequisites
- Python 3.11+
- Node.js 20+
- Optional: Redis (for background task queue). The app gracefully falls back to in‑process threads when Redis is not available.

## Setup
1. Clone and create a virtualenv:
   ```bash
   git clone https://github.com/your-org/GesahniV2.git && cd GesahniV2
   python -m venv .venv && source .venv/bin/activate
   ```
2. Install Python deps and prepare env:
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   ```
   Alternatively: `bash app/setup.sh`
3. Start the backend:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Start the frontend (in another shell):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Running Tests and Linters
Run these before pushing:
```bash
pytest -q
ruff check .
```
If you use Black locally:
```bash
black .
```
Type‑checking (optional):
```bash
pyright
```

## Branching and Commits
- Create feature branches off `main`.
- Write clear, imperative commit messages (e.g., "Add search endpoint").
- Keep diffs focused; unrelated reformatting should be avoided.

## Pull Request Checklist
- [ ] Tests pass locally (`pytest -q`)
- [ ] Lints are clean (`ruff check .`)
- [ ] Docs updated (e.g., `README.md`, `AGENTS.md`)
- [ ] Added/updated `.env.example` if new env vars were introduced
- [ ] Backwards compatibility considered (tests, API surface)

## Adding a New Skill
1. Create `app/skills/<name>_skill.py` implementing a `Skill` subclass with `PATTERNS` and `run()`.
2. Register it in `app/skills/__init__.py` to set execution order.
3. Add tests under `tests/test_skills/` (positive and negative cases).
4. Run tests and linters.

## Deterministic Router
- Enable via `DETERMINISTIC_ROUTER=1`.
- Tune thresholds in `router_rules.yaml` (hot‑reloaded). Override the path with `ROUTER_RULES_PATH`.

## Reporting Security Issues
Please open a private security advisory on your repository host (e.g., GitHub Security Advisories) or contact the maintainers privately. Avoid filing public issues for vulnerabilities.



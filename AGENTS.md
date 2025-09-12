# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI backend, skills, routing, and agents (e.g., `router.py` → `route_prompt`, `gpt_client.py` → `ask_gpt`, `llama_integration.py` → `ask_llama`, `home_assistant.py` → `handle_command`). Startup logic under `app/startup/`.
- `frontend/`: Next.js UI for interacting with the assistant.
- `tests/`: Pytest suite covering routing, skills, and utilities.
- `data/`, `sessions/`, `bench/`: Sample data, captured sessions, and embedding helpers.

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run LLaMA (Ollama): `ollama pull llama3 && ollama run llama3`
- Backend (dev): `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- Frontend (dev): `cd frontend && npm run dev`
- Smoke tests: `pytest -q tests/smoke`
- Full tests: `pytest -q`
- Load test (optional): `k6 run scripts/k6_load_test.js -e BASE_URL=http://127.0.0.1:8000` or `locust -f locustfile.py --host=http://127.0.0.1:8000`

## Coding Style & Naming Conventions
- Python: 4-space indent, PEP 8, type hints for new/modified code. Names: functions/vars `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE`.
- Frontend: Follow Next.js/React conventions; keep components functional and colocate module styles. If configured, run `npm run lint` before committing.
- Files: Python modules `snake_case.py`; tests `tests/test_<module>.py`.

## Testing Guidelines
- Framework: Pytest. Add positive and negative cases for new routes, skills, and utilities.
- Names: `test_*` functions in `tests/` mirroring module names.
- Fast checks: run `pytest -q tests/smoke` before PRs; prefer local fixtures and sample data over real network calls.

## Commit & Pull Request Guidelines
- Commits: small, focused, imperative subject lines (e.g., "Add timer skill parsing"). Conventional prefixes (`feat:`, `fix:`, `chore:`) are welcome.
- PRs: clear description, linked issues, screenshots for UI changes, and notes on env/config changes. Include tests and update docs (`README.md`, this file) when behavior changes.

## Security & Configuration Tips
- Do not commit secrets. Provide env via shell or `.env*` files excluded from VCS. Minimum for local dev: `OPENAI_API_KEY`, `HOME_ASSISTANT_TOKEN`.
- `/config` requires `ADMIN_TOKEN`. CORS requires exact origin: set `CORS_ALLOW_ORIGINS=http://localhost:3000` (not `127.0.0.1`).
- If OpenAI is unavailable, routing falls back to LLaMA. Configure `OLLAMA_URL` and `OLLAMA_MODEL` accordingly.

## Agent & Skill Authoring
- New skills: copy `app/skills/example_skill.py`, implement a `Skill` subclass with `PATTERNS` and `run()`, then register it in `app/skills/__init__.py`. Add tests under `tests/` and run `pytest -q`.

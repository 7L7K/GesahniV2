# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI backend with routing (`router.py`), GPT/LLaMA clients, skills, and startup hooks under `app/startup/`.
- `frontend/`: Next.js web UI that communicates with the backend assistant.
- `tests/`: Pytest suites that mirror backend modules and skills.
- `data/`, `sessions/`, `bench/`: Sample payloads, recorded interactions, and embedding helpers for experimentation.

## Build, Test, and Development Commands
- Install Python deps: `pip install -r requirements.txt`.
- Launch backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` for hot-reload API.
- Launch UI: `cd frontend && npm run dev` to start Next.js on port 3000.
- Run smoke tests: `pytest -q tests/smoke`; full suite: `pytest -q`.
- Optional LLaMA local model: `ollama pull llama3 && ollama run llama3` before routing requests to it.

## Coding Style & Naming Conventions
- Python uses 4-space indentation, PEP 8 formatting, and type hints on new or modified code.
- Name functions and vars in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE`.
- Frontend follows idiomatic React/Next patterns; keep components functional and colocate styles.
- Align files with naming patterns (`app/skills/example_skill.py`, `tests/test_<module>.py`).

## Testing Guidelines
- Write pytest tests for each new route or skill, covering success and failure paths.
- Use descriptive `test_*` functions and leverage local fixtures instead of real network calls.
- Run `pytest -q tests/smoke` before PRs; follow with `pytest -q` when ready to merge.

## Commit & Pull Request Guidelines
- Use small, imperative commit subjects (e.g., `feat: add timer skill parsing`).
- PRs should describe scope, link issues, include screenshots for UI changes, and note config/env updates.
- Update docs (README.md or this guide) whenever behavior changes.

## Security & Configuration Tips
- Keep secrets out of VCS; rely on shell exports or ignored `.env` files for `OPENAI_API_KEY` and `HOME_ASSISTANT_TOKEN`.
- `/config` requires `ADMIN_TOKEN`; set `CORS_ALLOW_ORIGINS=http://localhost:3000` exactly.
- Configure LLaMA fallback via `OLLAMA_URL` and `OLLAMA_MODEL` when OpenAI is unavailable.

## Agent & Skill Authoring
- New skills subclass `Skill`, define `PATTERNS`, implement `run()`, then register in `app/skills/__init__.py`.
- Start from `app/skills/example_skill.py` as a template and add focused pytest coverage under `tests/`.

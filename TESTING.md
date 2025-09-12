Testing Guide

Quick start
- Run tests: `pytest -q --disable-warnings --tb=short --maxfail=0 -rA --timeout=20`
- Lint/format/type: `ruff check --fix . && black . && mypy app tests`

Fixtures
- `client`: Synchronous FastAPI TestClient bound to the app.
- `async_client`: httpx.AsyncClient using ASGITransport with base `http://testserver`.
- `test_user`: Standard user dict with `user_id`, `username`, `password`, `email`.
- `cors_client`/`csrf_client`/`cors_csrf_client`: Async clients preconfigured for CORS/CSRF tests.

Auth cookies
- Use `from app.web.cookies import set_auth_cookies` in server code and tests to set the canonical cookie trio (access, refresh, session) with consistent attributes derived from `app.cookie_config.get_cookie_config()`.
- Use `from app.web.cookies import clear_auth_cookies` to clear them.

External calls
- Tests run with network calls disabled. LLM/OpenAI/Ollama/Chroma are replaced with in‑memory stubs in `conftest.py`.

Notes
- Optional vendor health checks are disabled in tests via env flags set in root `conftest.py`.
- Vector store defaults to `memory`; CHROMA_PATH is isolated per session.

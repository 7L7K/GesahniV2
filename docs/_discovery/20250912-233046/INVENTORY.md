# Inventory

Directories and key components
- Backend: `app/` (FastAPI app, routers, middleware, auth, health)
- Frontend: `web/` (Next.js 15 app dir scaffold)
- Tests: `tests/` (extensive suite)
- Data/session artifacts: `data/`, `sessions/` (runtime writes); DB/bolt files in repo root
- Dev orchestration: `docker-compose.yml`, `docker-compose.redis.yml`

Lockfiles and runtimes
- Python: `.python-version` → 3.11.9; `requirements.txt` (FastAPI 0.115.x, Uvicorn 0.35.0)
- Node: no top-level engines; Next.js pinned in `web/package.json`
  - Snippet (web/package.json:12–19):
    ```
    "dependencies": { "next": "15.4.4", "react": "19.1.0", ... }
    ```

Start/build scripts
- Backend (dev): `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
  - env-controlled bind shown in (app/main.py:1348–1354):
    ```
    host = os.getenv("HOST", "0.0.0.0"); port = int(os.getenv("PORT", 8000))
    uvicorn.run(full_app, host=host, port=port)
    ```
- Frontend (dev/build): (web/package.json:5–10)
  - `npm run dev` → `next dev`
  - `npm run build` → `next build`
  - `npm start` → `next start`

Ports and health
- Backend default: `:8000` (HOST/PORT envs). Health endpoints:
  - `/healthz` and `/v1/healthz` (app/api/health.py:51–86)
  - `/healthz/live`, `/healthz/ready` (app/api/health.py:88–120+)
  - `/metrics` (Prometheus) (app/api/metrics_root.py:24–41, 46–58)

Env vars (selected; see CONFIG_MATRIX for details)
- Security/cookies: `JWT_SECRET`, `JWT_KEYS`, `COOKIE_SAMESITE`, `COOKIE_SECURE`, `APP_DOMAIN`, `CSRF_ENABLED`, `CSRF_LEGACY_GRACE`
- CORS: `CORS_ORIGINS` or `CORS_ALLOW_ORIGINS`
- OAuth: `GOOGLE_CLIENT_ID`, `GOOGLE_REDIRECT_URI`, `OAUTH_REDIRECT_ALLOWLIST`, `FRONTEND_URL`, `APP_URL`
- Backend selection: `PROMPT_BACKEND` (openai|llama|dryrun)
- Vendors: `OPENAI_API_KEY`, `OLLAMA_URL`, `HOME_ASSISTANT_URL`/`HOME_ASSISTANT_TOKEN`
- Storage/queues: `REDIS_URL`, `SESSIONS_DIR`

Where referenced (examples)
- App creation and middleware:
  - `app/main.py` (793–915, 1095–1137) and `app/middleware/loader.py` (113–127)
- CORS env to list: `CORS_ORIGINS` or `CORS_ALLOW_ORIGINS` in `app/main.py` (900–915)
- Cookies policy: `app/cookie_config.py` (defaults and APP_DOMAIN handling)
  - Snippet (app/cookie_config.py:1–24):
    ```
    COOKIE_SECURE, COOKIE_SAMESITE, JWT_*_MINUTES ...
    get_cookie_config(request) -> { secure, samesite, domain, path, httponly }
    ```
- Whoami canonical: `app/api/auth.py` (943–964)
- Health/metrics: `app/api/health.py` and `app/api/metrics_root.py`
- WS: `app/api/music_ws.py` (origin allowlist fallback to CORS_ALLOW_ORIGINS)

Static assets, images, rewrites
- No `next.config.*` found. No image remote domains declared. No Next.js middleware or rewrites/redirects in repo.

Background workers/queues
- Uses `asyncio.create_task` in several places; token store cleanup scheduled on startup (app/main.py:420–431 approx.).
- Nightly jobs: `schedule_nightly_jobs()` (app/main.py:378–383, app/storytime.py)

WebSockets/SSE/streaming
- WS endpoints: `/v1/ws/music`, `/v1/ws/care` (e.g., app/api/music_ws.py:50–99)
- Streaming/SSE in LLM adapters and router handlers (app/llm_adapters.py, app/router/ask_api.py)

File uploads and disk writes
- Upload to `sessions/` via `SESSIONS_DIR` (app/session_store.py:16–20) and endpoints (app/api/sessions_http.py:31–45)
- Various JSONL history/audit writers under `data/` paths (e.g., app/history.py, app/audit_new/store.py)

Docker/Procfile
- Dockerfiles: none. Procfiles: none.
- docker-compose present for Postgres and Redis (dev only).

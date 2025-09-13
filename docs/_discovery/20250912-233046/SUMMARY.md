# Executive Summary

This repo contains a FastAPI backend (rich routing, cookie auth, CSRF, CORS) and a minimal Next.js 15 frontend under `web/`. Target migration: frontend → Vercel; backend → Render. This discovery is read‑only and surfaces concrete findings, risks, and a readiness plan.

What’s here
- Backend (FastAPI): entry in `app/main.py` with `create_app()` wiring routers, middleware, and startup checks.
  - App creation: `app/main.py` lines 793–801 show `FastAPI(...)` instantiation.
    - Snippet (app/main.py:793–801):
      ```
      app = FastAPI(
          title="GesahniV2",
          version=_get_version() or os.getenv("APP_VERSION", ""),
          lifespan=lifespan,
          openapi_tags=tags_metadata,
      )
      ```
  - Routers are registered centrally with versioned prefixes in `app/routers/config.py`.
    - Snippet (app/routers/config.py:46–59):
      ```
      core = _must([
          RouterSpec("app.router.ask_api:router", "/v1"),
          RouterSpec("app.api.auth:router", "/v1"),
          RouterSpec("app.api.google_oauth:router", "/v1/google"),
          RouterSpec("app.api.oauth_google:router", ""),
          ...
          RouterSpec("app.api.health:router", ""),
          RouterSpec("app.api.metrics_root:router", ""),
      ])
      ```
  - Middleware is canonicalized with CSRF and CORS in `app/middleware/loader.py`.
    - Snippet (app/middleware/loader.py:113–127):
      ```
      cors_enabled = bool(cors_origins and [o for o in cors_origins if o])
      if cors_enabled:
          app.add_middleware(CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=True,
            allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
            allow_headers=["Authorization","Content-Type","X-CSRF-Token"],
            expose_headers=["X-Request-ID","X-Error-Code","X-Error-ID","X-Trace-ID"],
            max_age=3600)
      ```
  - Health and metrics endpoints:
    - `/health`, `/healthz`, `/v1/healthz`, `/healthz/live`, `/healthz/ready` (app/api/health.py:18–120, 112–120+)
    - `/metrics` Prometheus (app/api/metrics_root.py:24–41, 46–58)
  - Canonical identity endpoint `/v1/whoami` (app/api/auth.py:943–964+).
    - Snippet:
      ```
      @router.get("/whoami", include_in_schema=False)
      async def whoami(...):
          # returns is_authenticated, session_ready, user, source
      ```
  - Startup/env wiring sets CSRF and CORS via env (app/main.py:889–914, 1095–1137 verification).
- Frontend (Next.js 15 / React 19) in `web/`:
  - `web/package.json` pins next@15.4.4, react@19.1.0 with scripts `dev`, `build`, `start`.
    - Snippet (web/package.json:5–16):
      ```
      "dev": "next dev", "build": "next build", "start": "next start"
      "next": "15.4.4", "react": "19.1.0", "react-dom": "19.1.0"
      ```
  - Minimal app dir: `web/src/app/layout.tsx`, `web/src/app/page.tsx`. No `next.config.*` or middleware.
- Auxiliary services/dev:
  - docker-compose for Postgres and Redis present for local dev: `docker-compose.yml`, `docker-compose.redis.yml`.
  - Python version: `.python-version` → 3.11.9.

How to run locally
- Backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` (env `HOST`/`PORT` defaults in app/main.py:1348–1354)
- Frontend: `cd web && npm run dev` (Next.js dev server on 3000)
- Optional services: `docker compose up -f docker-compose.yml -d` and `-f docker-compose.redis.yml -d`

Biggest migration risks
- Cross-site cookies + CSRF: Cookies default SameSite=Lax (configurable). If frontend and backend are on different apex domains or subdomains, you’ll likely need `COOKIE_SAMESITE=none` and TLS (forces Secure) and to send `X-CSRF-Token` from the client on unsafe methods. CORS is credentials-enabled and requires exact origins.
- Local disk writes: Upload/capture endpoints write under `SESSIONS_DIR` to repo-local `sessions/`. On serverless (Vercel Edge/functions) this will break. Render needs persistent disk or rewrite flows to object storage.
  - Snippet (app/api/sessions_http.py:31–45):
    ```
    session_dir = Path(SESSIONS_DIR)/session_id; session_dir.mkdir(...)
    dest = session_dir/"source.wav"; dest.write_bytes(await file.read())
    ```
- WebSockets and SSE: Multiple WS endpoints (e.g., `/v1/ws/music`, `/v1/ws/care`) and streaming. Vercel functions are not suitable for backend WS—must terminate on Render.
  - WS origin check uses `CORS_ALLOW_ORIGINS` fallback (app/api/music_ws.py:18–26).
- OAuth redirects: Google OAuth callbacks exist at multiple paths (`/v1/auth/google/callback`, `/auth/callback`, `/google/oauth/callback`). Domain correctness and allowlists must match Vercel/Render prod URLs.
- CORS drift: Middleware mounts only when `CORS_ORIGINS` or `CORS_ALLOW_ORIGINS` set. With `allow_credentials=True`, wildcards will be rejected by browsers. Must specify exact origins (e.g., https://app.example.com).

Showstoppers (potential)
- Any server-side file system writes on Vercel backend: Not supported. Must run backend on Render (recommended) or refactor to object storage.
- Missing `next.config.*` may be fine, but image domains and rewrites should be defined if needed. Currently no Next middleware/rewrites present.
- Ensure `JWT_SECRET` strength (enforced at startup) and cookie domain policy for cross-site. Production APP_DOMAIN is required if you want a shared cookie domain (app/cookie_config.py forces Secure/Lax when APP_DOMAIN is set).

Local/health endpoints summary
- Liveness: `/healthz/live` (200 always) and `/healthz`
- Readiness: `/healthz/ready` (200 with body indicating degraded/unhealthy)
- Canonical: `/v1/whoami`
- Metrics: `/metrics`

Target fit notes
- Vercel (frontend): No blocking use of Next.js Edge features. Minimal app; ensure `NEXT_PUBLIC_*` exposure as needed. No custom `next.config.*` today.
- Render (backend): Native build is suitable (Python 3.11 + pip install -r requirements.txt). Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Health check path: `/healthz/ready` or `/healthz/live`. Needs persistent disk if keeping local sessions, otherwise S3/GCS.

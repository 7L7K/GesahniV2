# Config Matrix

Environment variables (focused on migration-relevant)

| Name | Default | Dev example | Prod expectation | Used by (file:lines) |
|------|---------|-------------|------------------|----------------------|
| ENV | dev | dev | prod | app/main.py:833–855 |
| HOST | 0.0.0.0 | 127.0.0.1 | 0.0.0.0 | app/main.py:1348–1354 |
| PORT | 8000 | 8000 | $PORT (Render) | app/main.py:1348–1354 |
| PROMPT_BACKEND | dryrun | dryrun/openai/llama | openai/llama | app/main.py:889–914 |
| CORS_ORIGINS | (unset) | http://localhost:3000 | https://your-frontend.tld | app/main.py:900–915; app/middleware/loader.py:113–127 |
| CORS_ALLOW_ORIGINS | (legacy alias) | http://localhost:3000 | avoid; prefer CORS_ORIGINS | app/main.py:900–915; app/api/music_ws.py:23–26 |
| CSRF_ENABLED | 1 | 1 | 1 | app/main.py:900–915; app/middleware/loader.py (CSRFMiddleware) |
| CSRF_LEGACY_GRACE | 1 | 1 | 0 | app/csrf.py:18–33, 137–162 |
| COOKIE_SAMESITE | lax | lax | lax or none (cross-site) | app/cookie_config.py (policy), app/csrf.py:172–206 |
| COOKIE_SECURE | auto | 0 (dev over http) | 1 (prod TLS) | app/cookie_config.py:35–83 |
| APP_DOMAIN | (unset) | (unset) | your root cookie domain | app/cookie_config.py:98–115 |
| JWT_SECRET | (required) | long dev secret | long prod secret | app/main.py:214–239; app/api/auth.py:1151–1163 |
| JWT_KEYS/JWT_KEY_POOL | (optional) | JSON/dict | JSON/dict | app/api/auth.py:1188–1212 |
| JWT_EXPIRE_MINUTES | 30 | 30 | e.g., 15 | app/cookie_config.py:141–165 |
| JWT_REFRESH_EXPIRE_MINUTES | 1440 | 1440 | e.g., 43200 | app/cookie_config.py:167–176 |
| OAUTH_REDIRECT_ALLOWLIST | (unset) | localhost:3000 | prod hostnames | app/api/google_oauth.py:122–145 |
| FRONTEND_URL | (unset) | http://localhost:3000 | https://app.tld | app/api/google_oauth.py:1240, 1325 |
| APP_URL | (unset) | http://localhost:8000 | https://api.tld | app/api/google_oauth.py:1372 |
| GOOGLE_CLIENT_ID | (unset) | from .env | prod OAuth client | app/api/google_oauth.py:277 |
| GOOGLE_REDIRECT_URI | from .env.example | http://localhost:8000/v1/google/auth/callback | Vercel domain + path | .env.example:7 |
| OPENAI_API_KEY | (unset) | dev key | prod key | app/api/ask.py:756; adapters |
| OLLAMA_URL | (unset) | http://localhost:11434 | internal URL | app/main.py:520–545 |
| HOME_ASSISTANT_URL | (unset) | http://localhost:8123 | internal URL | app/api/ha.py:104 |
| HOME_ASSISTANT_TOKEN | (unset) | token | token | app/api/ha.py:104 |
| REDIS_URL | (unset) | redis://localhost:6379 | managed Redis | app/session_store.py:60–75 |
| SESSIONS_DIR | app/sessions | ./sessions | persistent mount | app/session_store.py:16–20 |
| ADMIN_TOKEN | (unset) | set for /v1/config | secret | app/status.py:29–41, 55–64 |
| PROMETHEUS_ENABLED | 1 | 1 | 1 | app/api/metrics_root.py:7 |

Cookie policy (from centralized config)

| Cookie | HttpOnly | Secure | SameSite | Domain | Path | Max-Age | Set at |
|--------|----------|--------|----------|--------|------|---------|--------|
| access (GSNH_AT or __Host-access_token) | true | dev: false; prod: true; forced true if SameSite=None | lax by default | None (dev) or APP_DOMAIN (prod) | / | JWT_EXPIRE_MINUTES*60 | app/web/cookies.py:174–180; app/cookie_config.py |
| refresh (GSNH_RT or __Host-refresh_token) | true | same as above | same | same | / | JWT_REFRESH_EXPIRE_MINUTES*60 | app/web/cookies.py:173–179 |
| session (GSNH_SESS or __Host-__session) | true | same as above | same | same | / | same as access | app/web/cookies.py:180–187 |
| csrf_token | false | forced true if SameSite=None | lax by default | None | / | ~1800 (default) | app/web/cookies.py:194–206; app/csrf.py mirrors header

Notes
- APP_DOMAIN when set in prod forces Secure=True and SameSite=Lax (app/cookie_config.py:98–115).
- If `COOKIE_SAMESITE=none`, Secure is forced true (RFC) even in dev; ensure TLS in preview/prod.

CORS policy (single Starlette CORSMiddleware)

| Property | Value |
|----------|-------|
| allow_origins | from `CORS_ORIGINS` (exact matches, deduped) |
| allow_credentials | true |
| allow_methods | GET, POST, PUT, PATCH, DELETE, OPTIONS |
| allow_headers | Authorization, Content-Type, X-CSRF-Token |
| expose_headers | X-Request-ID, X-Error-Code, X-Error-ID, X-Trace-ID |
| max_age | 3600 |
| Code refs | app/middleware/loader.py:113–127; app/main.py passes `cors_origins` |

OAuth/3P callbacks (Google)
- `/v1/auth/google/callback` (legacy compat endpoint) (app/api/oauth_google.py:7–21)
- `/auth/callback` (canonical handler) (app/api/google_oauth.py:464)
- `/google/oauth/callback` (root-level compat) (app/api/google_oauth.py:1952)
- Required prod URLs: set `GOOGLE_REDIRECT_URI` to Vercel prod domain path that maps to one of the above. Ensure allowlist via `OAUTH_REDIRECT_ALLOWLIST` includes the Vercel app domain.

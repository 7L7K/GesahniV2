# Routes and Health

Backend routes (key ones with auth notes)
- `/v1/whoami` GET — canonical identity; public; returns auth/session shape.
  - Ref: `app/api/auth.py:943–1008`
- Health
  - `/health` GET — simple up/degraded; public (app/api/health.py:18–48)
  - `/healthz` and `/v1/healthz` GET — 200 always; public (app/api/health.py:51–86)
  - `/healthz/live` GET — liveness; 200 always (app/api/health.py:88–109)
  - `/healthz/ready` GET — readiness; 200 with component statuses (app/api/health.py:112–220)
- Metrics
  - `/metrics` GET — Prometheus (app/api/metrics_root.py:24–41, 46–58)
- Status/observability
  - `/v1/status`, `/v1/rate_limit_status`, `/v1/google/status` — public observability (app/status.py:1–41, 79–113, 18–28)
- OAuth (Google)
  - `/v1/auth/google/callback` GET/POST (compat; clears state cookies) (app/api/oauth_google.py:7–35)
  - `/auth/callback` GET (canonical) (app/api/google_oauth.py:464)
  - `/google/oauth/callback` GET (compat) (app/api/google_oauth.py:1952)
- Sessions and uploads (Care)
  - `/v1/upload` POST — writes to `SESSIONS_DIR` (app/api/sessions_http.py:31–45)
  - `/v1/capture/*` POST — start/save/tags/status (app/api/sessions_http.py:48–120)
- WebSockets
  - `/v1/ws/music`, `/v1/ws/care` — WS endpoints with origin checks (app/api/music_ws.py:50–99; app/api/care_ws.py)
- Admin
  - `/v1/admin/*` — guarded via `require_scope` dependencies (e.g., app/api/admin.py)

Router registration and canonical prefix
- Central plan mounts routers with prefixes mostly under `/v1` (app/routers/config.py:46–90). Health and metrics are root-mounted for compatibility.

Auth requirements
- Many routes depend on `Depends(get_current_user_id)`; some admin routes require scopes (`require_scope`, `require_scopes`). Whoami is public, but reflects authentication state and may perform silent refresh if only refresh cookie present (app/api/auth.py:1000–1020).

Frontend API usage
- Current Next.js `web/` app contains no direct `fetch()` usage in the sources scanned. Tests mock an `apiFetch` helper (web/src/tests/a11y.test.tsx), indicating future client calls may centralize there.
- When implementing client requests for protected endpoints, use credentials: `include`, and pass `X-CSRF-Token` header for unsafe methods to satisfy CSRF.

Canonical endpoints summary
- Identity: `/v1/whoami`
- Health: `/healthz`, `/v1/healthz`, `/healthz/live`, `/healthz/ready`
- Metrics: `/metrics`
- OAuth callback(s): `/auth/callback`, `/v1/auth/google/callback`, `/google/oauth/callback`

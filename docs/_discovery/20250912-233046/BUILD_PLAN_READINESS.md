# Build/Deploy Readiness

## Vercel (Frontend)
- next.config.*: none found (defaults apply). No Middleware/Edge usage detected.
- Images: no `images.domains` configured; add if loading remote images.
- Server actions/SSR: minimal app; no custom server actions.
- Node runtime: Next 15; ensure Vercel project uses Node 20+.
- Env exposure: only `NEXT_PUBLIC_API_ORIGIN` in `.env.example` (line 44). Ensure any client-visible envs are prefixed `NEXT_PUBLIC_`.
- Fetch patterns: none yet; when added, use `credentials: 'include'` with CSRF header.

Checklist
- [ ] Add `NEXT_PUBLIC_API_ORIGIN` to Vercel envs (preview/prod)
- [ ] Add `images.remotePatterns` (if loading external images)
- [ ] Add `rewrites` if proxying to backend; or use direct API origin

## Render (Backend)
- Build: Python 3.11; `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/healthz/ready` (200 always; JSON status). Liveness: `/healthz/live`.
- WebSockets: supported on Render; terminate WS here (not on Vercel).
- Persistent disk: required for `SESSIONS_DIR` if keeping on local FS; otherwise shift to object storage.
- Cold start: moderate; avoid heavy vendor pings at boot unless needed (`STARTUP_VENDOR_PINGS=0`).

Checklist
- [ ] Set `PORT` (Render auto) and expose `/healthz/ready`
- [ ] Configure `CORS_ORIGINS` to exact Vercel URLs, `allow_credentials=true`
- [ ] Set cookie policy: `APP_DOMAIN`, `COOKIE_SAMESITE` (none for cross-site), `COOKIE_SECURE=1`
- [ ] Provide `JWT_SECRET` (>=32 chars) or key pool; enforce strength at startup
- [ ] Provide vendor envs: `OPENAI_API_KEY`, `OLLAMA_URL` (if used), HA envs (if used)
- [ ] Add `REDIS_URL` if enabling Redis-backed session store

Routing and middleware invariants
- Router plan centralization (app/routers/config.py) keeps canonical `/v1/*` mounts.
- CORS only mounts when origins provided; credentials=true; no wildcard.
- CSRF enforced when `CSRF_ENABLED=1`. For `COOKIE_SAMESITE=none` (cross-site), CSRF expects `X-CSRF-Token` header (see app/csrf.py).

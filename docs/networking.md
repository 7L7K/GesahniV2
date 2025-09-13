# Dev/Prod Networking Model

## TL;DR

- Dev: same-origin via Next.js rewrites (proxy mode). No CORS mounted.
- Prod (preferred): reverse-proxy API under the app origin (first-party cookies).
- Prod (cross-origin fallback): strict allowlist CORS + cookies `SameSite=None; Secure`.

## Why

Cross-origin + `credentials:'include'` + `SameSite=Lax` is fragile (localhost vs 127.0.0.1, Safari ITP, third‑party cookie deprecation). Proxying in dev keeps browsers first‑party and removes most cookie flakiness.

## Env knobs (and only these)

### Frontend

- `NEXT_PUBLIC_USE_DEV_PROXY` = `true|false`
- `NEXT_PUBLIC_API_ORIGIN` = `http://localhost:8000` (used by rewrites in dev; by API base when proxy is off)

### Backend

- `CORS_ALLOW_ORIGINS` (only if cross-origin in prod)
- `COOKIE_SAMESITE` (default `lax`)
- `COOKIE_SECURE` (dev `0`, prod cross-origin `1`)

## Dev recipe (same-origin)

```
# frontend/.env.local
NEXT_PUBLIC_USE_DEV_PROXY=true
NEXT_PUBLIC_API_ORIGIN=http://localhost:8000

# Run
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pnpm -C frontend dev
# visit /debug/env-canary
```

Expected:

- `mode: "proxy"`, whoami → 200, authenticated after login.
- No `CORSMiddleware` in backend middleware list.

## Prod recipes

### Preferred (same-origin via reverse proxy)

- Serve app and `/v1/*` from the same origin.
- Cookies: `SameSite=Lax`, `Secure=1`.

### Cross-origin fallback

```
CORS_ALLOW_ORIGINS=https://app.example.com
COOKIE_SAMESITE=none
COOKIE_SECURE=1
```

Rules:

- Exact `Access-Control-Allow-Origin` echo.
- `Access-Control-Allow-Credentials: true`.
- TLS mandatory (browsers ignore `SameSite=None` without `Secure`).

## Guardrails

- ESLint forbids absolute `http://localhost:8000` in client code.
- Playwright test fails if proxy mode leaks any absolute backend URLs.
- Backend pytest verifies zero CORS in proxy mode and exactly one CORS layer when configured.


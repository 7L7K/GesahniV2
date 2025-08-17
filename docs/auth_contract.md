# Auth Contract (Runtime-Truth)

## Endpoints (canonical)
- GET /v1/whoami → 200 JSON { is_authenticated:boolean, session_ready:boolean, user:{ id, email }|null, source:"cookie|header|missing", version:1 }
  - **LOCKED CONTRACT**: Always returns 200, never 401, never redirects, no caching
- GET /v1/sessions → 200 JSON [Session]
- GET /v1/sessions/paginated → 200 JSON { items:[Session], next_cursor?:string }
- POST /v1/auth/refresh → 200 JSON { access_token? } | 204 No Content
- POST /v1/auth/logout → 200 JSON { status:"ok" }
- POST /v1/auth/finish → 204 No Content
  - **LOCKED CONTRACT**: Always returns 204, idempotent (safe to call twice)

### Deprecated delegates (logged once)
- POST /v1/refresh → delegates to /v1/auth/refresh on 404/501 only
- POST /v1/logout  → delegates to /v1/auth/logout

## Cookies
- Access: `HttpOnly; Path=/; SameSite=Lax; Priority=High`
- Refresh: `HttpOnly; Path=/; SameSite=Lax; Priority=High`
- Cross-site silent refresh sets both with: `SameSite=None; Secure; Priority=High`
- Logout clears both with `Max-Age=0` (mirror SameSite used at set-time)

> Note: `Priority` is advisory; we never rely on it for correctness.

## CSRF & Headers
- CSRF sets `csrf_token` (not HttpOnly; SameSite=Lax).
- Mutating flows require `X-CSRF-Token` echo of the cookie **and** `X-Auth-Intent: refresh` for cross-site refresh.
- Refresh without refresh cookie → 401 even with headers (by design).

## Refresh Safety
- Single-use: token is consumed exactly once; replay → 401.
- Concurrency: if two calls race, one returns 200/204, the other 401 (replay).
- Local fallback for counters operates when Redis absent.

## Status Codes (normative)
- whoami: 200 (never 401, never redirect, no caching)
- auth/finish: 204 (always, idempotent)
- refresh: 200/204 | 401 (missing/expired/replay) | 429 (rate limit)
- logout: 200 | 401


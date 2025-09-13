# Upgrading to “Two‑Knob” Networking

## Breaking/Notable changes

- Removed layered CORS middlewares; now a single Starlette `CORSMiddleware` only when `CORS_ALLOW_ORIGINS` is set.
- Deleted `NEXT_PUBLIC_API_BASE`; use `NEXT_PUBLIC_API_ORIGIN`.
- Canonicalized `GET /v1/whoami`. Legacy `/whoami` is `308` to the canonical path (with `Deprecation` header).

## Do this

### Frontend envs

- Remove `NEXT_PUBLIC_API_BASE` everywhere.
- Add `NEXT_PUBLIC_USE_DEV_PROXY=true` for dev.

### Client code

- Replace absolute `http://localhost:8000/...` with relative paths (proxy mode) or use the shared `API_URL` helper when proxy is off.

### Backend

- Do not mount any custom CORS layers.
- Set `CORS_ALLOW_ORIGINS` only in cross-origin prod.

### Tests

- Keep/enable the new CORS/cookie pytest and Playwright tests.

## Verify

```
tools/cors_cookie_probe.sh http://localhost:8000 http://localhost:3000
# Expect: Set-Cookie on login, whoami returns authenticated
```

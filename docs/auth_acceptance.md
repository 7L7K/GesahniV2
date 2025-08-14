# Auth Acceptance Checklist

Goal: A new dev can validate sign-in/out, token behavior, per-user rate limits, role gates, device pairing, cache-key isolation, and retry norms in ≤60 minutes.

## Prerequisites
- Node.js 20+, Python 3.11+.
- Redis (optional but recommended) for device tokens and pairing codes (`REDIS_URL`).
- Clerk application with a Development instance.
- Local env configured per `docs/README-auth.md`.

## Environment sanity
1) Frontend `.env.local`:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...`
   - `NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in`
   - `NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up`
   - `NEXT_PUBLIC_API_URL=http://localhost:8000`
2) Backend env:
   - `JWT_SECRET=change-me`
   - Clerk JWKS:
     - Either `CLERK_JWKS_URL=https://<tenant>.clerk.accounts.dev/.well-known/jwks.json`
     - Or `CLERK_ISSUER=https://<tenant>.clerk.accounts.dev`
     - Optional `CLERK_AUDIENCE=<your-publishable-key-or-aud>`
   - Optional: `REDIS_URL=redis://localhost:6379/0`

## Sign-in / Sign-out
- Visit `http://localhost:3000/` signed-out → header shows Sign in/Sign up; homepage shows a signed-out notice.
- Click Sign in and complete with Clerk → after redirect, `UserButton` is visible in header.
- Click sign-out in the user menu → header returns to Sign in/Sign up.

## Silent rotation (server-side)
- Backend silently refreshes cookies near access expiry when enabled. For a quick smoke:
  - Set `ACCESS_REFRESH_THRESHOLD_SECONDS=3600` and ensure `JWT_SECRET` is set.
  - Perform a request; subsequent requests should continue to succeed without manual refresh.

## Per-user rate limits (keyed by user → device → IP)
- Terminal A (User A) get a token (via Clerk) and call a safe endpoint:
  ```bash
  curl -i -H "Authorization: Bearer $A" http://localhost:8000/v1/profile
  ```
  Observe `X-RateLimit-*` headers.
- Terminal B (User B) same IP, different token:
  ```bash
  curl -i -H "Authorization: Bearer $B" http://localhost:8000/v1/profile
  ```
  Headers show independent counters (no shared `remaining`).
- Admin routes use a separate bucket. Compare:
  ```bash
  curl -i -H "Authorization: Bearer $A" http://localhost:8000/v1/admin/metrics
  ```
  vs non-admin route; buckets are distinct (admin bucket suffix).

## Role gates (401 vs 403)
- Admin route (no admin role):
  ```bash
  curl -i -H "Authorization: Bearer $NON_ADMIN" http://localhost:8000/v1/admin/metrics
  ```
  Expect `403 Forbidden`.
- Admin route (admin role present in JWT `roles`):
  ```bash
  curl -i -H "Authorization: Bearer $ADMIN" http://localhost:8000/v1/admin/metrics
  ```
  Expect 200.
- Caregiver/resident routes (examples):
  - `POST /v1/care/alerts/{id}/ack` requires caregiver (403 otherwise).
  - `GET /v1/care/alerts` allows caregiver or resident.

## Device/TV pairing (scoped resident token)
- Start pairing (signed-in user):
  ```bash
  CODE=$(curl -s -X POST -H "Authorization: Bearer $USER" -H "X-Device-Label: tv-livingroom" \
    http://localhost:8000/v1/devices/pair/start | jq -r .code)
  echo $CODE
  ```
- Complete pairing (device):
  ```bash
  DEV=$(curl -s -X POST http://localhost:8000/v1/devices/pair/complete \
    -H 'Content-Type: application/json' -d '{"code":"'$CODE'"}')
  echo "$DEV" | jq
  DEV_TOKEN=$(echo "$DEV" | jq -r .access_token)
  ```
  The device token is restricted to resident scope (`care:resident`, role `resident`).
- Test resident-scoped access:
  ```bash
  curl -i -H "Authorization: Bearer $DEV_TOKEN" http://localhost:8000/v1/care/alerts
  ```
- Test admin denial with device token:
  ```bash
  curl -i -H "Authorization: Bearer $DEV_TOKEN" http://localhost:8000/v1/admin/metrics
  ```
  Expect 403.
- Revoke device token:
  ```bash
  curl -i -X POST -H "Authorization: Bearer $USER" \
    http://localhost:8000/v1/devices/tv-livingroom/revoke \
    -H 'Content-Type: application/json' -d '{"jti":"<copied-from-device-token>"}'
  ```
  Subsequent calls with revoked token should fail with 401.

## Cache-key isolation (frontend)
- With the UI running, log in as User A, navigate around (profile, state, music). Log out, then log in as User B: no cross-user cached data should appear.
- Change active device (e.g., play on a different device) — device-context queries should re-fetch (React Query keys include `device:<id>`).
- See `Cache Key Policy` in `src/lib/api.ts`.

## 429/5xx retry norms
- 429 responses include `Retry-After` and `X-RateLimit-*` headers. Frontend surfaces a `rate-limit` event; no auto-retry loop is performed.
- 5xx (and unknown) errors: React Query is configured to retry a max of 1 time for non-auth/non-429 errors.

## WebSocket handshake auth (bonus)
- Invalid Clerk/HS256 token on `/v1/ws/care` handshake → close with code 1008 and clear reason.
- Valid caregiver/resident token → accepted.

---
- Time budget: A focused run-through of the above should complete in ≤ 60 minutes.

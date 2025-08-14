### F1 — Login → Dashboard (Happy Path)

- Step 1: Open Login screen (frontend)
  - Screen: `frontend/src/app/login/page.tsx`
  - Action: user enters username/password and submits.
  - Proof: frontend/src/app/login/page.tsx — "const endpoint = mode === 'login' ? '/v1/login' : '/v1/register'" and "const res = await apiFetch(endpoint, { auth: false, method: 'POST', ... })"

- Step 2: Backend verifies credentials and issues tokens
  - Endpoint: POST `/v1/login` → `app/auth.py`
  - Server state: validates password, creates access/refresh JWT, sets HttpOnly cookies.
  - Proof: app/auth.py — "access_token = jwt.encode(access_payload, SECRET_KEY, algorithm='HS256')" and "response.set_cookie(key='access_token', value=access_token, httponly=True, ...)"

- Step 3: Client stores tokens (header mode) and sets auth hint
  - Client state: `setTokens(access_token, refresh_token)` and `auth:hint` cookie; redirect to next.
  - Proof: frontend/src/app/login/page.tsx — "if (access_token) setTokens(access_token, refresh_token)" and "document.cookie = `auth:hint=1; path=/; max-age=${14 * 24 * 60 * 60}`"

- Step 4: Navigate to dashboard `/` and hydrate auth
  - Screen: `frontend/src/app/page.tsx`; determines `authed` via header token or `/v1/whoami`.
  - Backend: GET `/v1/whoami` (from `app/main.py` core router) returns `user_id`.
  - Proof: frontend/src/app/page.tsx — "const res = await fetch('/v1/whoami', { credentials: 'include' });" and "setAuthed(Boolean(body && (body.is_authenticated || body.user_id !== 'anon')));"

- Step 5: Dashboard loads music state
  - Client: calls `getMusicState()` → GET `/v1/state` guarded by auth.
  - Server: `app/api/music.py@get_state` returns `StateResponse`.
  - Proof: frontend/src/lib/api.ts — "export async function getMusicState(): Promise<MusicState> { const res = await apiFetch(`/v1/state`, { auth: true }) }"

- Step 6: Dashboard opens WS for live music updates
  - Client: connects to `/v1/ws/music` with token when header mode.
  - Server: `app/api/music.py@ws_music` verifies WS and `accept()`s; broadcasts `music.state`.
  - Proof: frontend/src/app/page.tsx — "const url = wsUrl('/v1/ws/music'); ws = new WebSocket(url);"

- Step 7: Dashboard shows Now Playing, Discovery, Mood, Queue, Device
  - UI state: `musicState` renders `NowPlayingCard`, `DiscoveryCard`, etc.
  - Proof: frontend/src/app/page.tsx — "{authed && musicState && ( <NowPlayingCard state={musicState} /> )}"

- Step 8: User sends first message
  - Client: `sendPrompt()` posts to `/v1/ask` with SSE.
  - Server: `app/api/ask.py@ask` streams tokens via `StreamingResponse` and routes to model/skills.
  - Proof: frontend/src/lib/api.ts — "const res = await apiFetch('/v1/ask', { method: 'POST', headers, body: JSON.stringify(payload) });"

- Step 9: Server enforces auth and rate limit
  - Middleware/deps: `verify_token` + `rate_limit` (attached on routes and via middleware headers).
  - Proof: app/main.py — "protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])"

- Step 10: Dashboard stores chat locally and scrolls
  - Client state: `localStorage` persists messages by user id; auto-scroll updates.
  - Proof: frontend/src/app/page.tsx — "localStorage.setItem(historyKey, JSON.stringify(messages.filter(m => !m.loading).slice(-100)))"

### Unhappy paths (end-to-end)

- 401 → refresh → retry
  - Behavior: `apiFetch` auto-attempts POST `/v1/refresh` (cookie mode) or refresh token path (header mode). On success, retries original request with updated headers; on failure, clears tokens and surfaces refresh response.
  - Proof: `frontend/src/lib/api.ts` lines around 124–144.

- 403 missing scope
  - Behavior: Admin and caregiver-privileged endpoints enforce scopes (e.g., `admin:write`, `care:caregiver`). UI should show a permission error and avoid repeated retries.
  - Proof: scope enforcement via `app/deps/scopes.py` and route dependencies in `app/api/admin.py` and `app/api/care.py`.

- 429 rate limited with Retry-After
  - Behavior: `apiFetch` dispatches a `rate-limit` event including `Retry-After` and `X-RateLimit-Remaining`. UI toast shows countdown and disables inputs briefly; SSE/chat calls should avoid immediate retry.
  - Proof: `frontend/src/lib/api.ts` 108–123 and `frontend/src/app/page.tsx` includes `<RateLimitToast />`.

- 5xx transient with retry-after (problem+json or plain)
  - Behavior: For idempotent GETs, implement a single backoff retry after `Retry-After` seconds when present. For POST/SSE, surface the error and allow manual retry. Backend may return RFC7807 with `retry_after`.

- SSE disconnect mid-response
  - Behavior: In `sendPrompt`, if the SSE stream ends early, accumulated text is returned; the UI should show a soft warning and enable a quick resend button.

- WebSocket reconnect with backoff
  - Behavior: `wsUrl` constructs URL with token; the WS manager should implement exponential backoff on disconnect, resubscribe to topics, and surface a small offline badge.
  - Proof: `frontend/src/services/wsHub.ts` manages reconnect/backoff (documented in `C2_WebSocketFlows.md`).

### CSRF posture (verify path end-to-end)

- Policy: All mutating requests include `X-CSRF-Token` header when cookies are used. The header is read from `csrf_token` cookie and attached automatically in `api.ts` for methods with a body.
- Verification step:
  1) Clear cookies and attempt a POST `/v1/profile` without `X-CSRF-Token`. Expect 400/403 from server middleware.
  2) Obtain a `csrf_token` cookie (issued at login or preflight), retry POST `/v1/profile` with token auto-attached by `apiFetch` — expect 200.
- Proof: `frontend/src/lib/api.ts` sets `X-CSRF-Token` for POST/PUT/PATCH/DELETE; server `app/csrf.py` middleware validates header and rejects missing/invalid tokens.

### Local storage bounds & privacy

- Bounds: Only the last 100 messages are stored client-side per user.
- Per-user keying: Keys are derived from the authenticated `user_id` (e.g., `chat:{user_id}`). This prevents cross-account bleed on shared devices.
- PII posture: Avoid storing raw PII beyond the bounded history. For higher sensitivity, consider encrypting chat payloads at rest in the browser using Web Crypto with a device-bound key, and clearing on logout.
- Suggested config:
  - Encrypt messages with AES-GCM using a key derived from a device secret (rotated on logout/device revoke).
  - Periodic purge job removes entries older than N days or exceeding 100 items.

### Security headers & transport

- CSP: Nonce-based CSP applied by the backend; frontends should inject `nonce` for inline scripts/styles from `X-CSP-Nonce` header.
- HSTS: Enabled in production on HTTPS with `max-age=63072000; includeSubDomains; preload`.
- WS: `connect-src` restricted to the current host over `wss:` in production.

### JWT/session lifetimes

- Access: 15 minutes default (override with `JWT_ACCESS_TTL_SECONDS`).
- Refresh: 7–30 days via `JWT_REFRESH_TTL_SECONDS` or `JWT_REFRESH_EXPIRE_MINUTES`.
- Claims: `iss`/`aud` validated when configured; strict clock skew via `JWT_CLOCK_SKEW_S`.

### Rate-limit UI behavior

- On 429, the toast shows remaining and a countdown from `Retry-After`. The client refrains from automatic retries for POST/SSE; for GETs, optional single retry after countdown can be enabled for list views.

### Narrated Flow (7–10 steps)
1) I open Login and submit credentials; the page POSTs `/v1/login` with JSON. The server validates and sets `access_token`/`refresh_token` cookies. 2) The client stores tokens in header mode and drops an `auth:hint` cookie, then redirects to `/`. 3) On the dashboard, the app checks auth via header token or calls `/v1/whoami` to confirm a non‑anon user id. 4) It fetches initial music state from `/v1/state` and renders the cards. 5) It opens a WebSocket to `/v1/ws/music` for live updates and updates `musicState` on `music.state` messages. 6) I type a message; the client calls `/v1/ask` with SSE and streams assistant tokens into the last chat bubble. 7) Server dependencies `verify_token` and `rate_limit` guard routes; rate-limit headers render toasts when hit. 8) The message history is persisted to `localStorage` scoped by user id and the view auto-scrolls to the bottom.

### Where I got this (8+)
- `frontend/src/app/login/page.tsx`: "const endpoint = mode === 'login' ? '/v1/login' : '/v1/register'"
- `app/auth.py`: "response.set_cookie( key='access_token', value=access_token, httponly=True, ... )"
- `frontend/src/app/login/page.tsx`: "if (access_token) setTokens(access_token, refresh_token)"
- `frontend/src/app/page.tsx`: "const res = await fetch('/v1/whoami', { credentials: 'include' })"
- `app/main.py`: "@_core.get('/whoami') ... return {'user_id': user_id}"
- `frontend/src/lib/api.ts`: "export async function getMusicState() { const res = await apiFetch('/v1/state', { auth: true }) }"
- `frontend/src/app/page.tsx`: "const url = wsUrl('/v1/ws/music'); ws = new WebSocket(url);"
- `app/api/music.py`: "@ws_router.websocket('/ws/music') async def ws_music(ws: WebSocket, _user_id: str = Depends(get_current_user_id))"
- `frontend/src/lib/api.ts`: "const res = await apiFetch('/v1/ask', { method: 'POST', headers, body: JSON.stringify(payload) });"
- `app/main.py`: "protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])"
- `frontend/src/app/page.tsx`: "localStorage.setItem(historyKey, JSON.stringify(messages.filter(m => !m.loading).slice(-100)))"



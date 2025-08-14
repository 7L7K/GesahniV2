app/integrations/google/routes.py

- Purpose
  - Google OAuth integration endpoints: build auth URL, login-specific URL, handle OAuth callback, expose Gmail/Calendar helpers, and a simple status. Issues app JWTs and sets cookies on successful login. Persists Google tokens per user.
- Inputs
  - Query: next, code, state, error, error_description
  - Env: GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI, APP_URL, APP_JWT_SECRET/ALG/EXPIRE_MINUTES/REFRESH_EXPIRE_MINUTES
  - Cookies: pkce_verifier, oauth_state, oauth_next
  - Request: used for client IP/session scaffolding via sessions_store
- Outputs/side-effects
  - Redirects to Google OAuth URL; Redirects back to app with access_token and refresh_token as query params; sets HttpOnly access_token and refresh_token cookies; writes GoogleToken rows; ensures user_store entries; creates device session via sessions_store.create_session on login path; logs audit via INFO entries.
- Callers & callees
  - Called by: frontend login page via /v1/google/auth/login_url and browser OAuth redirect to /v1/google/oauth/callback
  - Calls:
    - .config.validate_config
    - .oauth.build_auth_url, .oauth.exchange_code, .oauth._verify_state, .oauth.creds_to_record
    - app.integrations.google.db.SessionLocal and GoogleToken
    - app.sessions_store.sessions_store.create_session
    - app.user_store.user_store.ensure_user, increment_login
    - PyJWT encode
- Control flow
  - Happy path
    - GET /auth/login_url: build URL with state(login=true,next), return {auth_url}
    - OAuth callback: validate state/code; exchange for tokens; derive email/sub; persist provider creds; create app session (sid,did); mint app access+refresh JWTs; set HttpOnly cookies; redirect to APP_URL/login?access_token=...&refresh_token=...&next=...
  - Failure paths
    - Missing config → 500 google_oauth_unconfigured
    - Google token exchange/userinfo fails → redirect to app /login with error query
    - Missing id_token/user info → 400/redirect with error
- Security & limits
  - No explicit rate limit enforced here; relies on upstream middleware. Cookies set with Secure when https or SameSite=None; samesite from env. No CSRF on redirect.
- Edge cases
  - Openssl missing on backup path not used here. Next URL allowlist via _allow_redirect for some endpoints (main routes.py uses its own logic). Callback tolerates missing email by using sub.
- Receipts
  - app/integrations/google/routes.py:
    - "Return {\"auth_url\": url}"; "redirect with tokens in the URL to satisfy client bootstrap flow in tests"
  - Unknown: OAuth state signing/validation details → see app/integrations/google/oauth.py

app/middleware.py

- Purpose
  - Cross-cutting HTTP middlewares and helpers: request ID assignment, duplicate request deduplication, rich request tracing/logging/metrics, silent access-token refresh via cookies, environment hot-reload.
- Inputs
  - Headers: X-Request-ID, Authorization, X-Forwarded-For, X-Session-ID, X-Channel
  - Cookies: access_token, refresh_token
  - Env: multiple (DEDUP_TTL_SECONDS/MAX_ENTRIES; JWT_SECRET; ACCESS_REFRESH_THRESHOLD_SECONDS; COOKIE_SECURE/SAMESITE; RELOAD_ENV_ON_REQUEST; etc.)
- Outputs/side-effects
  - Sets response headers: X-Request-ID, X-Trace-ID, Server-Timing, RateLimit headers, security headers; optionally sets X-Local-Mode cookie; refreshes access_token/refresh_token cookies when near expiry; records metrics and persists history/decisions.
- Callers & callees
  - Called by FastAPI as middleware (added in app/main.py)
  - Calls: user_store.ensure_user/increment_request, analytics record_latency/latency_p95, metrics counters/histograms, decisions/history appenders, security.get_rate_limit_snapshot, env_utils.load_env, jwt.decode/encode
- Control flow
  - Happy path
    - RequestIDMiddleware assigns/propagates X-Request-ID
    - DedupMiddleware rejects duplicate in-TTL requests (409)
    - trace_request logs timing, anonymized user id, metrics; adds security and rate-limit headers; persists history/decision; sets trace id headers
    - silent_refresh_middleware: after handler returns, checks cookie access_token exp vs threshold; if near, mints new token and resets cookies; may re-set refresh cookie TTL
  - Failure paths
    - Dedup: if seen, return 409 with Retry-After TTL
    - Trace: catches TimeoutError/Exception to set rec.status and re-raise; still records latency in finally
    - Silent refresh: best-effort; wrapped in try/except, never breaks response
- Security & limits
  - Dedup TTL cache to mitigate retries; security headers (HSTS/CSP); redacts Authorization in logs; rate-limit headers are informational (actual enforcement in security.rate_limit per-route).
- Edge cases
  - JWT decode errors tolerated; refresh only when JWT_SECRET present; jitter sleep to avoid herd during refresh. Hot-reload env opt-in.
- Receipts
  - "Duplicate request" 409 with Retry-After; "silent_refresh_middleware" code issuing set_cookie for access_token; CSP header string.

app/security.py

- Purpose
  - Authentication helpers (verify_token/verify_ws), HTTP and WS rate limiting (local or Redis), nonce and webhook verification, headers snapshots.
- Inputs
  - Headers: Authorization (Bearer), X-Forwarded-For, Cookie (access_token), X-Nonce
  - WS query: token/access_token; WS headers Authorization/Cookie
  - Env: JWT_SECRET, RATE_LIMIT*, REDIS_URL, DAILY_REQUEST_CAP, REQUIRE_JWT/ENFORCE_JWT_SCOPES, TRUST_X_FORWARDED_FOR, RATE_LIMIT_KEY_SCOPE, RATE_LIMIT_BYPASS_SCOPES, NONCE_TTL_SECONDS, etc.
- Outputs/side-effects
  - Raises HTTPException/WebSocketException on auth/limit violations; increments Prometheus metrics; maintains in-memory and/or Redis counters; sets request.state.jwt_payload; returns problem+json on custom limiter.
- Callers & callees
  - Called by: route dependencies and middlewares (e.g., rate_limit, verify_token, verify_ws)
  - Calls: jwt decode; Redis client; metrics; helper functions within file
- Control flow
  - Happy path (verify_token)
    - If JWT_SECRET missing and REQUIRE_JWT off (or tests): allow
    - Else prefer Authorization Bearer; fallback to access_token cookie; decode; attach payload to request.state or raise 401
  - Rate limit
    - Compose key by user or IP; consider route scoping; apply optional daily cap; use Redis if available, else in-memory; enforce burst then long windows; include Retry-After
  - WS auth
    - Inspect header/query/cookie for token; decode if secret present; attach payload; proceed even if missing (anon allowed)
  - Failure paths
    - Missing/invalid token when required → 401
    - Rate limits exceeded → 429 (HTTP) / WS close 1013, with headers for retry
- Security & limits
  - Scope enforcement helper; bypass scopes; per-scope limiter; problem+json rate-limit for UX
- Edge cases
  - Test-mode refresh of env; robust fallbacks when Redis missing; daily caps keyed by test id to avoid cross-test bleed
- Receipts
  - Code blocks showing verify_token, rate_limit, verify_ws logic; headers returned.

app/auth.py

- Purpose
  - Username/password auth: register, login, refresh, logout; enforces username/password policy; sets cookies; session/PAT scaffolding integrations.
- Inputs
  - JSON bodies: {username,password}, {refresh_token}, {token,new_password}
  - Headers: Authorization (for logout), X-Forwarded-For
  - Env: USERS_DB, JWT_SECRET, JWT_EXPIRE_MINUTES, JWT_REFRESH_EXPIRE_MINUTES, PASSWORD_STRENGTH, COOKIE_*; optional ISS/AUD
- Outputs/side-effects
  - Writes to SQLite (users); sets HttpOnly cookies access_token/refresh_token; revokes refresh family with in-memory set; increments user_store stats; returns TokenResponse
- Callers & callees
  - Called by frontend login/register; refresh by middleware/client; logout by UI
  - Calls: aiosqlite for users; passlib for hashing; token_store.{allow_refresh,is_refresh_allowed,is_refresh_family_revoked}; user_store; jwt encode/decode
- Control flow
  - Happy path
    - Register: validate username/password; insert into auth table; mirror legacy projections; return {status:ok}
    - Login: throttle attempts; fetch hash; verify; mint access/refresh with jti; set cookies; update stats; return tokens
    - Refresh: verify refresh; rotate family (revoke old jti, mint new pair); reset cookies; return tokens
    - Logout: require Bearer; decode; mark access jti revoked; clear cookies
  - Failure paths
    - Invalid username/password, duplicate username → 400/401
    - Rate limited → 429 with retry_after
    - Invalid refresh → 401; invalid issuer/aud → 401
- Security & limits
  - Rate-limit login attempts per IP/user; revocation store for refresh families; cookies set Secure/SameSite per env; passlib
- Edge cases
  - Legacy tables mirrored; password strength optional via zxcvbn or heuristic; test-mode DB pathing
- Receipts
  - "@router.post('/login')", cookie set blocks; refresh rotation using revoked_tokens and token_store family checks

app/sessions_store.py

- Purpose
  - Minimal device session DB separate from auth tables: create device session (sid,did), list user sessions, rename device, revoke family ids.
- Inputs
  - Params: user_id, did?, device_name?; path: sid
  - Env: USER_DB path for SQLite file
- Outputs/side-effects
  - Writes to SQLite device_sessions and revoked_families; returns lists for API.
- Callers & callees
  - Called by: app/api/auth.py (session listing), app/api/oauth_google.py (create_session), app/api/me.py, app/api/sessions.py
  - Calls: aiosqlite
- Control flow
  - Happy path
    - create_session: insert (sid,did,user_id,device_name,timestamps)
    - list_user_sessions: select rows for user ordered by last_seen
    - rename_device: update device_name for did
    - revoke_family: mark family id in revoked table and set matching sid revoked
  - Failure paths
    - DB exceptions bubble; methods close connections in finally
- Security & limits
  - No direct auth here; callers enforce
- Edge cases
  - Table creation (if not exists) each call; best-effort marking revoked
- Receipts
  - "CREATE TABLE IF NOT EXISTS device_sessions"; return dict with keys sid,did

Unknowns and next files to open
- Google OAuth helper details: app/integrations/google/oauth.py
- Where UI creates PATs or sessions pages call these: already covered; device-bound refresh checks happen in app/api/auth.py::rotate_refresh_cookies and app/token_store.py (opened above for family revocation keys)

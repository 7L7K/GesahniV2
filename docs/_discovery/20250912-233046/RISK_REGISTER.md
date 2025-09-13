# Risk Register

| Rank | Risk | Evidence | Mitigation |
|------|------|----------|------------|
| High | Local disk writes incompatible with serverless | Upload/capture write to `SESSIONS_DIR` (app/api/sessions_http.py:31–45); SESSIONS_DIR defaults to repo `sessions/` (app/session_store.py:16–20) | Run backend on Render with persistent disk; or refactor to S3/GCS and presigned uploads |
| High | Cross-site cookie + CSRF/CORS misconfig | Credentials=true CORS (app/middleware/loader.py:113–127), default SameSite=Lax; cross-site needs `COOKIE_SAMESITE=none` and CSRF header (app/csrf.py:172–206) | Set exact `CORS_ORIGINS`, `COOKIE_SAMESITE=none`, `COOKIE_SECURE=1`; ensure client sends `X-CSRF-Token` and uses `credentials: include` |
| High | Missing strong JWT secret in prod | Startup enforces length (app/main.py:214–239) and auth code requires secret (app/api/auth.py:1151–1163) | Provide >=32 char `JWT_SECRET` or proper key pool (`JWT_KEYS`) in Render env |
| Medium | OAuth callback domains mismatch | Multiple callback routes; allowlist via `OAUTH_REDIRECT_ALLOWLIST` (app/api/google_oauth.py:122–145) | Set `GOOGLE_REDIRECT_URI` to Vercel domain and update allowlist/domains in Google console |
| Medium | WS termination on Vercel | WS endpoints (app/api/music_ws.py, app/api/care_ws.py) | Terminate WS on Render only; Next should not host backend WS |
| Medium | Unset CORS origins leads to dev-only behavior | CORS only mounts if origins provided (app/middleware/loader.py) | Ensure `CORS_ORIGINS` is set in Render; include Vercel app URLs |
| Low | Image domains missing | No next.config.* images config | Add `images.remotePatterns` if using remote images |
| Low | Vendor health checks at boot increase startup time | Startup checks configurable; enforced strictly in prod paths | Keep `STARTUP_VENDOR_PINGS=0` or set timeouts appropriately |

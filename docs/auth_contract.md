Auth Contract Artifact (generated)

- GET /v1/whoami
  - Response: { is_authenticated: boolean, session_ready: boolean, user: { id: string|null, email: string|null }|null, source: "cookie"|"header"|"missing", version: 1 }
  - Headers: Authorization optional
  - Cookies read: access_token
  - Status: 200 always, fields mark readiness
- GET /v1/sessions
  - Response: SessionInfo[]
  - Headers: Auth required
- GET /v1/sessions/paginated
  - Response: { items: SessionInfo[], next_cursor?: string|null }
  - Headers: Auth required
- POST /v1/auth/refresh
  - Headers: X-Auth-Intent: refresh when SameSite=None; X-CSRF-Token when CSRF_ENABLED=1
  - Response: { status: "ok", user_id: string, access_token?: string, refresh_token?: string }
  - Cookies set: access_token (HttpOnly; Path=/; SameSite; Secure; Priority=High), refresh_token (same)
  - Status: 200 on success; 401 on replay/family revoked; 429 on RL
- GET /v1/auth/finish; POST /v1/auth/finish
  - POST requires CSRF when enabled; sets cookies as above; GET redirects
- POST /v1/auth/logout
  - Headers: X-CSRF-Token when CSRF_ENABLED=1
  - Behavior: revoke refresh family; clear cookies

Deprecated (delegating with warning): POST /v1/refresh, POST /v1/logout


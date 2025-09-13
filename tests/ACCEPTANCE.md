# Networking Acceptance Checklist

- `/debug/env-canary` shows `mode: "proxy"` in dev.
- Backend middleware list contains 0 `CORSMiddleware` in dev.
- `tools/cors_cookie_probe.sh` shows `Set-Cookie` on login and authed `whoami`.
- Playwright: no absolute `localhost:8000` requests in proxy mode.
- If prod cross-origin: one `CORSMiddleware`, exact `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials: true`, cookies `SameSite=None; Secure`.


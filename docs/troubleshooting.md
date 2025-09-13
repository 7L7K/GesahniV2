## Troubleshooting: Cookies & CORS

### Symptom → Fix

- Login works, whoami unauth in XHR → You’re cross-origin in dev. Turn on proxy: `NEXT_PUBLIC_USE_DEV_PROXY=true`.
- CORS preflight 403/blocked → Using credentials with `*`. Set `CORS_ALLOW_ORIGINS=https://app.example.com` exactly; never wildcard with credentials.
- Safari only fails → You’re in third‑party cookie land. Use proxy or set `SameSite=None; Secure` on real TLS.
- 127.0.0.1 vs localhost mismatch → Same issue: cross-origin. Use proxy or pin a single host everywhere.

### Quick checks

- Visit `/debug/env-canary` and confirm `mode: "proxy"` in dev, and that `/v1/whoami` returns 200 with cookies.
- Run `tools/cors_cookie_probe.sh` to validate `Set-Cookie` and subsequent `whoami` with a cookie jar.
- On prod cross-origin, confirm exact `Access-Control-Allow-Origin` echo and `Access-Control-Allow-Credentials: true`.

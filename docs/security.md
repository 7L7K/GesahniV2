Security hardening notes

- CSP: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https: wss:; font-src 'self' data:; frame-ancestors 'none'
- HSTS: Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
- CORS: configure allowed origins via env `CORS_ALLOW_ORIGINS` (comma CSV)
- Webhook secret rotation: POST `/v1/admin/reload_env` after updating secret file; use `/v1/admin/flags` to toggle behaviors at runtime
- Pre-commit secret scanning: `pre-commit install` then commits are scanned using detect-secrets. Update baseline via `detect-secrets scan > .secrets.baseline`.

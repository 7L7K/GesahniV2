# Dev Login Guide

This guide helps you test the end-to-end authentication flow in dev environment.

## Prerequisites
- Server running on http://127.0.0.1:8000
- ENV=dev (default)
- Dev user "dev_user" with password "devpass123!" is auto-seeded on startup

## Login
```bash
curl -i -c /tmp/gsn.cookies \
  -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:8000/v1/login \
  --data '{"username":"dev_user","password":"devpass123!"}'
```

Expected response:
- HTTP/1.1 200 OK
- Set-Cookie: access_token=...; HttpOnly; Secure; SameSite=Lax
- Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Lax
- Set-Cookie: __session=...; HttpOnly; Secure; SameSite=Lax

## Me Endpoint
```bash
curl -i -b /tmp/gsn.cookies http://127.0.0.1:8000/v1/whoami
```

Expected response:
- HTTP/1.1 200 OK
- Body: `{"user": {"id": "dev_user", "auth_source": "header", "auth_conflict": false}, "stats": {"login_count": 1, "request_count": 1, "last_login": "2025-09-05T10:55:00Z"}, "sub": "dev_user"}`

# Cookie-Based Authentication Setup for Browser-First Development

## Overview

Your GesahniV2 project is now configured for **cookie-based authentication** in browser-first development mode. This setup is safer and simpler than header-based authentication for web applications.

## Configuration Summary

### ✅ Environment Variables Set

```bash
# Turn off header mode, enable cookie mode
export NEXT_PUBLIC_HEADER_AUTH_MODE=0
```

### ✅ Backend CORS Configuration

The FastAPI backend is properly configured with:

```python
# CORS configuration in app/main.py
_cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").strip().lower() in {"1", "true", "yes", "on"}

# CORSMiddleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,  # ✅ Allows cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type", "x-csrf-token", "x-requested-with", "x-request-id", "x-auth-intent"],
    expose_headers=["X-Request-ID", "X-CSRF-Token", "Retry-After", "RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset"],
    max_age=600,
)
```

### ✅ Frontend API Configuration

All authenticated requests use `credentials: 'include'` by default:

```typescript
// frontend/src/lib/api.ts
export async function apiFetch(
  path: string,
  init: (RequestInit & { auth?: boolean; dedupe?: boolean; shortCacheMs?: number; contextKey?: string | string[]; credentials?: RequestCredentials }) = {}
): Promise<Response> {
  const { auth = true, headers, dedupe = true, shortCacheMs, contextKey, credentials = 'include', ...rest } = init as any;
  // ... rest of implementation
}
```

### ✅ Auth Finisher Endpoint

The auth finisher correctly returns **204 with Set-Cookie headers**:

```python
# app/api/auth.py - POST /v1/auth/finish
if method == "POST":
    resp = _Resp(status_code=204)  # ✅ Returns 204
    # Set HttpOnly cookies
    resp.set_cookie("access_token", access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=token_lifetime, path="/")
    resp.set_cookie("refresh_token", refresh_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=refresh_life, path="/")
    return resp
```

### ✅ Cookie Configuration

Cookies are properly configured for development:

- **HttpOnly**: `True` (prevents XSS)
- **Path**: `/` (available across the app)
- **SameSite**: `Lax` (default, works for same-site requests)
- **Secure**: `False` in development (HTTP), `True` in production (HTTPS)

## How It Works

1. **Login Flow**: User logs in → backend sets HttpOnly cookies → frontend receives 204 response
2. **API Requests**: All requests include `credentials: 'include'` → cookies sent automatically
3. **Authentication**: Backend reads `access_token` cookie for authentication
4. **Refresh**: Backend uses `refresh_token` cookie for token rotation

## Benefits

- **Safer**: HttpOnly cookies prevent XSS attacks
- **Simpler**: No manual token management in frontend
- **Automatic**: Cookies sent with every request
- **Secure**: CSRF protection built-in
- **Mobile Ready**: Works seamlessly when you add mobile clients later

## Development URLs

- **Frontend**: `http://localhost:3000`
- **Backend**: `http://127.0.0.1:8000`
- **CORS Origins**: `http://localhost:3000`

## Testing

To verify the setup is working:

1. Start the backend: `cd app && python -m uvicorn main:app --reload --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. Navigate to `http://localhost:3000`
4. Try logging in - cookies should be set automatically
5. Check browser dev tools → Application → Cookies to see HttpOnly cookies

## Migration to Mobile

When you're ready to ship a mobile client:

1. **Keep cookie mode** for web clients
2. **Add header mode** for mobile clients by setting `NEXT_PUBLIC_HEADER_AUTH_MODE=1` in mobile builds
3. **Backend supports both** simultaneously - no changes needed

The current setup provides the best of both worlds: simple cookie auth for web and flexible header auth for mobile when needed.

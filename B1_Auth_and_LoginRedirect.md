### Pass/Fail matrix (redirect landing on /login?access_token=...&refresh_token=...&next=/)

- PASS — Legacy Google integration sets HttpOnly cookies on the RedirectResponse before redirecting to the app (and includes tokens in the query for bootstrap).
- FAIL — Modern Google OAuth callback sets cookies on one Response but returns a different Response for the 302; cookies are not guaranteed to be on the redirect.
- PASS — On landing at /login?... the frontend stores tokens and calls /v1/refresh with credentials to set HttpOnly cookies server-side.
- PASS — Root flow checks auth via /v1/whoami (and /v1/me), which depend on get_current_user_id and verify_token to read Authorization header or access_token cookie.

### Direct answers
- Do tokens get persisted to HttpOnly cookies server-side before redirect?
  - Yes in the legacy Google integration redirect flow. No in the modern Google OAuth handler (frontend completes it via /v1/refresh).
- If not, who does it?
  - The frontend `/login` page: captures query tokens, persists header tokens, and POSTs `/v1/refresh` to set HttpOnly cookies.
- How does `/` check auth?
  - Via `/v1/whoami` and `/v1/me`, using `get_current_user_id` and `verify_token` (header first, then cookie).

### Auth Flow Narrative
1) OAuth redirect (legacy) → API sets cookies on redirect; client lands on `/login?access_token=...&refresh_token=...&next=/` and can proceed immediately.
2) OAuth redirect (modern) → API currently returns a 302 built on a different Response from the one cookies were set on. Frontend compensates by calling `/v1/refresh` after landing on `/login` to ensure HttpOnly cookies are established.
3) Username/password login → `/v1/login` issues access+refresh, sets HttpOnly cookies, returns tokens for header mode.
4) App auth checks → `/v1/whoami` (and `/v1/me`) use header or `access_token` cookie via `get_current_user_id`/`verify_token`.
5) Silent refresh → middleware rotates `access_token` cookie near expiry and extends `refresh_token` best-effort.

### Where I got this (quotes and paths)

```231:269:app/integrations/google/routes.py
# Set HttpOnly cookies on the API domain before redirecting so that
# subsequent requests are authenticated server-side without relying on
# client storage.
resp = RedirectResponse(url=f"{app_url}/login?{query}")
resp.set_cookie(
    key="access_token",
    value=access_token,
    httponly=True,
    secure=cookie_secure,
    samesite=cookie_samesite,
    max_age=access_max_age,
    path="/",
)
resp.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,
    secure=cookie_secure,
    samesite=cookie_samesite,
    max_age=refresh_max_age,
    path="/",
)
return resp
```

```139:155:app/api/oauth_google.py
response.set_cookie("access_token", access, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=EXPIRE_MINUTES * 60, path="/")
response.set_cookie("refresh_token", refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=REFRESH_EXPIRE_MINUTES * 60, path="/")
...
resp = Response(status_code=302)
resp.headers["Location"] = next_url
return resp
```

```21:31:frontend/src/app/login/page.tsx
const access = params.get('access_token');
const refresh = params.get('refresh_token') || undefined;
if (access) {
  // Persist in header mode for SPA; also ensure server cookies via refresh
  setTokens(access, refresh);
  document.cookie = `auth:hint=1; path=/; max-age=${14 * 24 * 60 * 60}`;
  // Fire-and-forget to backend to rotate/ensure HttpOnly cookies
  fetch('/v1/refresh', { method: 'POST', credentials: 'include' }).finally(() => {
      router.replace(next);
  });
}
```

```459:561:app/auth.py
@router.post("/refresh", ...)
async def refresh(req: RefreshRequest | None = None, request: Request = None, response: Response = None) -> TokenResponse:
    ...
    # Set refreshed cookies for browser clients
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=REFRESH_EXPIRE_MINUTES * 60,
        path="/",
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token=access_token)
```

```376:379:app/main.py
@_core.get("/whoami")
async def _whoami(user_id: str = Depends(_get_uid), _r: None = Depends(_rl)):
    return {"user_id": user_id}
```

```42:67:app/api/me.py
@router.get("/whoami")
async def whoami(request: Request, user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    ...
    return {
        "is_authenticated": user_id != "anon",
        "user_id": user_id,
        ...
    }
```

```91:108:app/api/auth.py
@router.get("/whoami")
async def whoami(request: Request, user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    ...
    return {
        "is_authenticated": user_id != "anon",
        "user_id": user_id,
        ...
    }
```

```34:61:app/deps/user.py
# Try JWT-based user_id (Authorization bearer, WS query param, or cookie)
auth_header = target.headers.get("Authorization") if target else None
... if token is None and request is not None: token = request.cookies.get("access_token")
```

```418:459:app/security.py
async def verify_token(request: Request) -> None:
    jwt_secret = os.getenv("JWT_SECRET")
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    request.state.jwt_payload = payload
```

```376:436:app/middleware.py
async def silent_refresh_middleware(request: Request, call_next):
    ...
    if exp - now <= threshold:
        new_token = jwt.encode(new_payload, secret, algorithm="HS256")
        response.set_cookie(
            key="access_token",
            value=new_token,
            httponly=True,
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=lifetime,
            path="/",
        )
```


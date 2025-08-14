### Ranked Risks and One-liner Fixes (with receipts)

1) OAuth cookies-before-redirect bug (cookies set on wrong Response)
- Risk: Cookies are set on `response` but the handler returns a different `Response` for the 302; cookies won’t be persisted on the redirect.
- Fix (one-liner concept): Return the same Response you set cookies on. Replace creating a fresh `resp` with returning `response` after setting `Location`.
- Quote:
```139:155:app/api/oauth_google.py
response.set_cookie("access_token", access, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=EXPIRE_MINUTES * 60, path="/")
response.set_cookie("refresh_token", refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=REFRESH_EXPIRE_MINUTES * 60, path="/")
...
resp = Response(status_code=302)
resp.headers["Location"] = next_url
return resp
```
- One-liner: `response.status_code = 302; response.headers["Location"] = next_url; return response`
- Rank: High blast radius, Low effort.

2) Auth vs rate-limit order on /v1/ask (rate limit may count unauthenticated differently than intended)
- Risk: `/v1/ask` applies `Depends(rate_limit)` at route decorator, while auth is enforced inside handler; this can skew user-keying and leak rate-limit metadata pre-auth.
- Fix: Enforce `verify_token` dependency at decorator (behind the same env gate) or move rate_limit inside after `verify_token`.
- Quote:
```51:57:app/api/ask.py
@router.post(
    "/ask",
    dependencies=[Depends(rate_limit)],
```
```96:100:app/api/ask.py
if _require_auth_for_ask():
    await verify_token(request)
    # rate_limit applied via route dependency;
```
- One-liner: `dependencies=[Depends(verify_token), Depends(rate_limit)]` (guarded by env if needed).
- Rank: High blast radius, Medium effort (needs env-gated wrapper dep).

3) Unauthenticated WS broadcasts possible (subscribe before auth binding)
- Risk: WS handler calls `verify_ws(ws)` but still accepts connection and allows `subscribe` without scope checks; topics can be subscribed by anonymous clients if JWT_SECRET unset.
- Fix: Require `verify_ws` before `accept()` and enforce scope/topic ACL (at least require JWT when secret is set).
- Quote:
```89:96:app/api/care_ws.py
@router.websocket("/ws/care")
async def ws_care(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    await verify_ws(ws)
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("action") == "subscribe":
```
- One-liner: `await verify_ws(ws); await ws.accept()` → `await verify_ws(ws); if not getattr(ws.state, "user_id", None): return await ws.close()`
- Rank: High blast radius, Low effort.

4) Admin router missing explicit auth dependency (scope dependency optional)
- Risk: Admin API uses `optional_require_any_scope` only; if scopes enforcement is off via env, endpoints may be reachable with only the soft token check in `_check_admin` depending on env flags.
- Fix: Add `Depends(verify_token)` at router level to consistently require a valid JWT when JWT_SECRET is set.
- Quote:
```33:36:app/api/admin.py
router = APIRouter(tags=["Admin"], dependencies=[Depends(optional_require_any_scope(["admin", "admin:write"]))])
```
- One-liner: `router = APIRouter(tags=["Admin"], dependencies=[Depends(verify_token), Depends(optional_require_any_scope(["admin", "admin:write"]))])`
- Rank: Medium blast radius, Low effort.

5) Vector-store fallback can mask desync in production
- Risk: On backend init failure, code may silently fall back to MemoryVectorStore when not in strict/production, potentially causing reads/writes to diverge between processes if mixed modes occur.
- Fix: Tie fallback to a single env (`STRICT_VECTOR_STORE`) and ensure production-like envs never fall back; log and expose health in status.
- Quote:
```110:127:app/memory/api.py
except Exception as exc:
    if os.getenv("ENV", "").lower() == "production" or _strict_mode():
        logger.error("FATAL: Vector store init failed: %s", exc)
        raise
    ...
    store = MemoryVectorStore()
```
- One-liner: `if _strict_mode(): raise` (and set STRICT_VECTOR_STORE=1 in all non-dev deploys).
- Rank: Medium blast radius, Low effort.

6) OAuth legacy vs modern inconsistency (query tokens vs cookie-only)
- Risk: Legacy Google integration sets cookies on RedirectResponse and passes tokens via query; modern handler does cookie-only and (due to bug above) may drop cookies on redirect; frontend compensates but increases coupling.
- Fix: Standardize: set cookies on the actual redirect response and avoid query token leakage; or keep query tokens but always set cookies on the returned response.
- Quote:
```231:269:app/integrations/google/routes.py
resp = RedirectResponse(url=f"{app_url}/login?{query}")
resp.set_cookie(...)
return resp
```
```139:155:app/api/oauth_google.py
response.set_cookie(...)
resp = Response(status_code=302)
resp.headers["Location"] = next_url
return resp
```
- One-liner: Align `oauth_google.py` with legacy pattern: `resp = RedirectResponse(url=next_url); resp.set_cookie(...); return resp`.
- Rank: Medium blast radius, Low effort.

7) Missing rate-limit dependency on WS router include
- Risk: WS router is included without a dedicated rate-limit dependency; handler uses `verify_ws` but no burst control at handshake level could allow abuse.
- Fix: Attach `Depends(rate_limit_ws)` at router level or ensure accept is delayed until verification and per-connection throttles apply.
- Quote:
```1317:1319:app/main.py
app.include_router(care_ws_router, prefix="/v1")
app.include_router(care_ws_router, include_in_schema=False)
```
- One-liner: Include WS router with `dependencies=[Depends(rate_limit_ws)]` or add burst checks at subscribe.
- Rank: Medium blast radius, Medium effort.

### Where I got this
- OAuth cookies-before-redirect bug:
```139:155:app/api/oauth_google.py
response.set_cookie(...)
resp = Response(status_code=302)
resp.headers["Location"] = next_url
return resp
```
- Legacy OAuth cookies on redirect:
```231:269:app/integrations/google/routes.py
resp = RedirectResponse(url=f"{app_url}/login?{query}")
resp.set_cookie(...)
return resp
```
- /v1/ask auth vs rate-limit order:
```51:57:app/api/ask.py
@router.post(
    "/ask",
    dependencies=[Depends(rate_limit)],
```
```96:100:app/api/ask.py
if _require_auth_for_ask():
    await verify_token(request)
```
- WS broadcast and auth:
```89:101:app/api/care_ws.py
async def ws_care(ws: WebSocket, _user_id: str = Depends(get_current_user_id)):
    await verify_ws(ws)
    await ws.accept()
    ... subscribe ...
```
- Admin router scope dependency only:
```33:33:app/api/admin.py
router = APIRouter(tags=["Admin"], dependencies=[Depends(optional_require_any_scope(["admin", "admin:write"]))])
```
- Vector-store fallback path:
```110:127:app/memory/api.py
except Exception as exc:
    if os.getenv("ENV", "").lower() == "production" or _strict_mode():
        ...
    store = MemoryVectorStore()
```
- WS router include without explicit rate-limit dep:
```1317:1318:app/main.py
app.include_router(care_ws_router, prefix="/v1")
```

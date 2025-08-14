### Gesahni: Verified Flows — Executive Summary

This document summarizes verified flows across core areas (Auth, Router, Frontend, WebSockets, Memory/RAG, TV Scheduler, Home Assistant). It is grounded with code receipts and includes next-step fixes.

## One-page overview
- Purpose: Smart assistant blending local LLaMA and GPT with Home Assistant control, memory, and TV UI.
- Architecture: FastAPI backend (`app/main.py`), modular routers under `app/api/*`, deterministic model router, Qdrant/Chroma vector backends, Next.js frontend, WS for realtime UI.
- Security: JWT auth (cookies/headers), per-route deps (`verify_token`, `rate_limit`), nonce guard, webhook signing, optional Redis for rate limiting.
- Ops UX: Admin endpoints for metrics/config/traces; proactive engine hooks; TV scheduler.

## Bullets per area

- Auth
  - Login issues JWT access/refresh, sets HttpOnly cookies; FE can also store tokens in header mode.
  - Refresh endpoint rotates tokens; logout revokes.

- Router
  - Request path: skills/HA → QA cache → deterministic router (self-check escalation) → GPT/LLaMA with provenance.
  - SSE used for streaming `/v1/ask` responses.

- Frontend
  - Next.js app hydrates auth via header token or `/v1/whoami`; stores chat history per user.
  - Music widgets + chat compose; model picker; rate-limit toast.

- WebSockets
  - Music updates via `/v1/ws/music`; Care topic hub at `/v1/ws/care` with subscribe/ping.
  - Frontend `wsHub` manages reconnect/backoff, auth probing.

- Memory/RAG
  - Vector backends: Memory, Chroma, Qdrant, Dual; QA cache with deterministic IDs.
  - New retrieval pipeline: dense+sparse Qdrant → RRF → MMR → rerank → boosts with explain trace.

- TV
  - Scheduler selects primary widget and side rail; next-event chip; scene nudges.
  - Ambient/tiles adapt to time-of-day and freshness.

- Home Assistant
  - States/services with validation and risky-action confirmation; aliases; resolve entities.
  - Signed webhooks; HA health surfaced in status.

## Text flow diagrams

- Auth (Login)
  - User → FE Login page → POST /v1/login → set cookies + optional header tokens → FE redirect → GET /v1/whoami → authed dashboard

- Router (/v1/ask)
  - FE SSE POST /v1/ask → BE rate_limit + verify_token → skills/HA or cache → deterministic router → GPT/LLaMA stream → SSE to FE

- Frontend (Dashboard init)
  - FE load / → check header token or /v1/whoami → getMusicState → open WS /v1/ws/music → hydrate widgets

- WebSockets (Music)
  - FE wsUrl(.../ws/music) → WS handshake with token/cookie → server verify_ws → accept → push music.state events

- Memory/RAG
  - Router needs docs → pipeline: embed query → Qdrant dense/sparse → RRF → MMR → rerank → boost → trim → explain_trace

- TV (Scheduler)
  - Tick → compute scores (importance, time, freshness, prefs) → assign primary/sideRail → scene nudge → overlay (dev)

- Home Assistant (Service call)
  - FE → POST /v1/ha/service (nonce) → validate service + confirm risky → call HA → log/audit → return

## Receipts (15)
- Auth cookies set
```app/auth.py
response.set_cookie(
  key="access_token",
  value=access_token,
  httponly=True,
```
- FE login submits
```frontend/src/app/login/page.tsx
const endpoint = mode === 'login' ? '/v1/login' : '/v1/register'
```
- Whoami
```app/main.py
@_core.get("/whoami")
async def _whoami(...):
  return {"user_id": user_id}
```
- Frontend whoami usage
```frontend/src/app/page.tsx
const res = await fetch('/v1/whoami', { credentials: 'include' });
```
- Protected router deps
```app/main.py
protected_router = APIRouter(dependencies=[Depends(verify_token), Depends(rate_limit)])
```
- SSE ask
```app/api/ask.py
resp = StreamingResponse(generator, media_type=media_type, ...)
```
- Deterministic routing + cache key
```app/router.py
cache_key = compose_cache_id(decision.model, norm_prompt, mem_docs)
```
- RAG pipeline thresholds
```app/retrieval/pipeline.py
"policy": "keep if sim>=0.75 (dist<=0.25)"
```
- Qdrant dense filter
```app/retrieval/qdrant_hybrid.py
kept = [it for it in items if (1.0 - float(it.score)) <= 0.25]
```
- Vector store selection
```app/memory/api.py
raw_kind = (os.getenv("VECTOR_STORE") or "").strip().lower()
```
- WS verify
```app/security.py
async def verify_ws(websocket: WebSocket) -> None:
```
- Music WS route
```app/api/music.py
@ws_router.websocket("/ws/music")
```
- FE WS connect
```frontend/src/lib/api.ts
return `${base}${path}${sep}access_token=${encodeURIComponent(token)}`
```
- TV scheduler assign
```frontend/src/services/scheduler.ts
const sideRail = scores.slice(1, 4).map(s => s.id);
```
- HA service
```app/main.py
@ha_router.post("/ha/service")
```

## Top 10 Fix-Next (ranked)
1) Tighten auth error handling parity FE/BE (normalize messages, unify 400/401 cases).
2) Add CSRF header integration to FE `apiFetch` for all mutating requests consistently in header mode.
3) Expand WS auth: refresh/reauth path for expired bearer during handshake; unify `handle_reauth` for care/music.
4) Vector backends: expose active backend and collection in `/v1/status` even when memory store is used; add health pings for Qdrant.
5) Router: persist deterministic `explain_trace` IDs and expose `/v1/admin/retrieval/last` filters in UI; show sources hover in FE.
6) TV scheduler: persist simple user prefs (hide tile X) and honor in scorers; add quiet-hours guard to ticker.
7) HA: surface `confirm_required` UX end-to-end (toast + confirm action) and list risky actions per domain in docs.
8) Rate limit: add Redis health indicator to status UI and suggest fallback path when down.
9) Security headers: make CSP configurable per env (images/fonts CDNs) and document in README.
10) Tests: add E2E covering login+whoami+WS connect happy path; add unit tests for `/v1/ask` SSE error framing.

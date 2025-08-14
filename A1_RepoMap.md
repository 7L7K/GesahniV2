### Gesahni — Baseline Repo Map (Phase A)

- Backend APIs
  - FastAPI app in `app/main.py`; versioned routers under `app/api/` are mounted for auth, admin, ask/chat, music, TTS, calendar, HA, sessions, TV, RAG, etc.
  - Key routers: `app/api/ask.py`, `app/api/admin.py`, `app/api/auth.py`, `app/api/ha.py`, `app/api/music.py`, `app/api/tts.py`, `app/api/calendar.py`, `app/api/rag.py`, `app/api/care_ws.py`, `app/api/tv.py`.

- Middleware/Security
  - `app/middleware.py`: request ID, tracing/telemetry, deduplication, security headers, silent token refresh, rate‑limit headers.
  - `app/security.py`: JWT verification for HTTP and WebSocket, dual‑bucket rate limiting (long + burst), optional Redis backend, per-scope overrides, nonce guard, webhook HMAC verification.

- Auth/Session stores
  - HTTP auth flows in `app/auth.py` (register/login/refresh/logout); cookie + header token patterns.
  - Persistent auth/session data in SQLite via `app/auth_store.py` (users, devices, sessions, PATs, audit_log).
  - `app/deps/user.py`: extracts current `user_id` from Authorization/cookies/WS params; tolerant in test/dev.

- Memory/Vector store
  - Abstraction in `app/memory/api.py` and `app/memory/vector_store/` with backends: in‑memory, Chroma (`app/memory/chroma_store.py`), Qdrant/dual (`app/memory/vector_store/qdrant.py`, `dual.py`).
  - Selection via env `VECTOR_STORE` with safe fallbacks; QA cache access via `qa_cache` proxy; memory add/query helpers.

- Retrieval/RAG
  - Hybrid retrieval pipeline in `app/retrieval/pipeline.py` using Qdrant dense + sparse, RRF, MMR, local/hosted rerank, boosts, budget trimming, explain traces.
  - Qdrant helpers in `app/retrieval/qdrant_hybrid.py`; admin RAG search endpoint at `app/api/rag.py`.

- LLM routing
  - High‑level router in `app/router.py`: skills → HA → QA cache → deterministic router → self‑check escalation; provenance tags and caching.
  - Deterministic rules in `app/model_router.py` (hot‑reload via YAML); picks GPT models, composes cache IDs, runs self‑check escalation.
  - Providers: local LLaMA via Ollama (`app/llama_integration.py`), OpenAI via `app/gpt_client.py`.

- Voice/TTS
  - TTS orchestrator `app/tts_orchestrator.py` (OpenAI TTS vs local Piper with budget/privacy controls) + API `app/api/tts.py`.
  - STT/transcription flows in `app/transcription.py`; WS transcription endpoints wired from `app/main.py` into `app/api/sessions`.

- Home Assistant
  - Core client and command handling in `app/home_assistant.py` (states/services, validation, risky‑action confirmations, alias/entity resolution).
  - API in `app/api/ha.py`; HA webhook signing/verification in `app/security.py` and `/v1/ha/webhook` mounting from `app/main.py`.

- Integrations
  - Google OAuth under `app/integrations/google/`; Spotify client under `app/integrations/music_spotify/client.py`; SMS helper `app/integrations/twilio_sms.py`.

- Jobs
  - Admin‑triggered Qdrant lifecycle and Chroma→Qdrant migration via `app/jobs/qdrant_lifecycle.py` and `app/jobs/migrate_chroma_to_qdrant.py` (exposed in `app/api/admin.py`).

- Admin/Diagnostics
  - `app/api/admin.py`: metrics, router decisions, retrieval traces, config, vector store ops, flags, errors; `app/status.py`/`app/api/status_plus.py` expose health, limits, budget, vector backend, feature flags.

- Proactive/TV
  - Proactive engine hooks (nightly jobs, curiosity prompts) wired via `app/main.py` optional imports; TV endpoints in `app/api/tv.py` and frontend TV scheduler/UI under `frontend/src/app/tv/` and `frontend/src/services/scheduler.ts`.

- WebSockets
  - Music WS `app/api/music.py:/ws/music` for state/queue updates; Care WS hub `app/api/care_ws.py:/ws/care` for topic broadcasts; frontend hub `frontend/src/services/wsHub.ts` connects to both.

- Frontend
  - Next.js app in `frontend/` with pages under `frontend/src/app/*`, UI components in `frontend/src/components/*`, services (`api.ts`, `wsHub.ts`, `scheduler.ts`), tests under `frontend/src/**/__tests__` and Playwright e2e under `e2e/`.

- Entry points
  - `app/main.py` creates `FastAPI` app, mounts routers, CORS/middleware, Prometheus `/metrics`, and in `__main__` runs `uvicorn`.

- Config
  - Environment‑driven config across modules; comprehensive variables listed in `README.md` (LLMs, rate limits, vector store, RAG, HA, cookies, etc.). Admin `/v1/admin/config` overlays live vector settings.

### UNKNOWNs (<15)
- HA event subscription/long‑poll specifics beyond `ws/care` broadcasts.
- Detailed implementation of `app/proactive_engine` (only optional hooks referenced here).
- Twilio SMS integration flow (referenced but not mapped here).
- Full UI for admin “inspect” extras (mounted when present).
- Exact persistence format for QA cache when non‑Chroma (in‑memory vs dual).
- Full OAuth Apple flow details (router present; not deeply mapped).
- Voice input hardware capture specifics beyond `transcription` and sessions.
- Reranker “hosted” backend details (passthrough used when enabled).

### Where I got this (Receipts)
- `app/main.py`:
  - "app = FastAPI( title=\"Granny Mode API\", ... openapi_tags=tags_metadata, ... )"
  - "app.include_router(core_router, prefix=\"/v1\") ... app.include_router(auth_router, prefix=\"/v1\")"

- `app/api/ask.py`:
  - "@router.post(\n    \"/ask\", ... dependencies=[Depends(rate_limit)], ... )"
  - "resp = StreamingResponse( generator, media_type=media_type, status_code=status_code or 200 )"

- `app/security.py`:
  - "async def verify_token(request: Request) -> None: \"\"\"Validate JWT from Authorization header or HttpOnly cookie ...\"\"\""
  - "async def verify_ws(websocket: WebSocket) -> None: \"\"\"JWT validation for WebSocket connections. ...\"\"\""
  - "_RATE_LIMIT_BACKEND = os.getenv(\"RATE_LIMIT_BACKEND\", \"memory\").strip().lower()"

- `app/middleware.py`:
  - "class DedupMiddleware(BaseHTTPMiddleware): \"Reject requests with a repeated `X-Request-ID` header.\""
  - "response.headers.setdefault(\"Content-Security-Policy\", \"default-src 'self'; ... connect-src 'self' https: wss:; ...\")"

- `app/deps/user.py`:
  - "Return the current user's identifier. Preference order: ... JWT ... Fallback to anonymous."

- `app/memory/api.py`:
  - "def _get_store() -> VectorStore: \"\"\"Return the configured vector store backend. * `VECTOR_STORE` env-var controls ... Falls back to in-memory ...\"\"\""

- `app/memory/chroma_store.py`:
  - "\"\"\"Chroma-backed vector store implementation.\"\"\""
  - "embed_kind = os.getenv(\"CHROMA_EMBEDDER\", \"length\").strip().lower() ... OpenAIEmbeddingFunction ... model_name=os.getenv(\"EMBED_MODEL\", \"text-embedding-3-small\")"

- `app/retrieval/pipeline.py`:
  - "def run_pipeline(...): \"\"\"Execute the end-to-end retrieval pipeline and return (texts, trace).\"\"\""
  - "\"policy\": \"keep if sim>=0.75 (dist<=0.25)\""

- `app/retrieval/qdrant_hybrid.py`:
  - "# Enforce keep threshold sim>=0.75 (dist<=0.25)"

- `app/router.py`:
  - "use_new_pipeline = os.getenv(\"RETRIEVAL_PIPELINE\", \"0\").lower() in {\"1\", \"true\", \"yes\"}"
  - "decision = route_text(...); cache_key = compose_cache_id(decision.model, norm_prompt, mem_docs)"

- `app/model_router.py`:
  - "\"\"\"Deterministic model router with self-check escalation and cache keys.\nThis module centralizes routing ... hot-reloadable via a YAML rules file ...\"\"\""

- `app/llama_integration.py`:
  - "OLLAMA_URL = os.getenv(\"OLLAMA_URL\", \"http://localhost:11434\"); OLLAMA_MODEL = os.getenv(\"OLLAMA_MODEL\", \"llama3:latest\")"

- `app/gpt_client.py`:
  - "Thin wrapper around the OpenAI chat API." and "OPENAI_MODEL = os.getenv(\"OPENAI_MODEL\", GPT_MID_MODEL)"

- `app/tts_orchestrator.py`:
  - "\"\"\"Central orchestrator: picks engine, enforces budget, fallbacks, logs metrics.\"\"\""

- `app/api/tts.py`:
  - "router = APIRouter(prefix=\"/tts\", tags=[\"Music\"])" and "@router.post(\"/speak\", ...)"

- `app/home_assistant.py`:
  - "HOME_ASSISTANT_URL = os.getenv(\"HOME_ASSISTANT_URL\", \"http://localhost:8123\")" and "async def startup_check() ... logger.info(\"Connected to Home Assistant successfully\")"

- `app/api/music.py`:
  - "@ws_router.websocket(\"/ws/music\") ... await verify_ws(ws)"

- `app/api/care_ws.py`:
  - "Connect to `/v1/ws/care` and send a JSON message to subscribe to a topic. Example payload: {\"action\":\"subscribe\", ...}"

- `frontend/src/lib/api.ts`:
  - "export function wsUrl(path: string): string { ... return `${base}${path}${sep}access_token=${encodeURIComponent(token)}`; }"

- `frontend/src/services/wsHub.ts`:
  - "this.connect(\"music\", \"/v1/ws/music\", ...); this.connect(\"care\", \"/v1/ws/care\", ...);"

- `app/api/admin.py`:
  - "@router.get(\"/admin/metrics\") ... return { 'metrics': m, 'cache_hit_rate': cache_hit_rate(), ... }"
  - "from app.jobs.qdrant_lifecycle import bootstrap_collection ... from app.jobs.migrate_chroma_to_qdrant import main as _migrate_cli"

- `app/status.py`:
  - "_get_vector_store() ... out['vector_backend'] = name ... if 'dual' in name: ..."

- `README.md`:
  - "Enable with env: `DETERMINISTIC_ROUTER=1`. ... | `VECTOR_STORE` | `chroma` | ... (`memory`, `chroma`, `qdrant`, `dual`, or `cloud`)"



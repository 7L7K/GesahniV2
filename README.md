### Deterministic Model Router

- A new module `app/model_router.py` implements deterministic routing across text and vision with self-check escalation.
- Thresholds live in `router_rules.yaml` (hot-reloaded):
  - MAX_SHORT_PROMPT_TOKENS=240
  - RAG_LONG_CONTEXT_THRESHOLD=6000
  - DOC_LONG_REPLY_TARGET=900
  - OPS_MAX_FILES_SIMPLE=2
  - SELF_CHECK_FAIL_THRESHOLD=0.60
  - MAX_RETRIES_PER_REQUEST=1
- Enable with env: `DETERMINISTIC_ROUTER=1`.
- Override rules file location with env: `ROUTER_RULES_PATH=router_rules.yaml`.
- System prompts: `app/prompts/granny_mode.txt` and `app/prompts/computer_mode.txt`.

# GesahniV2
# 🦙✨ LLaMA-GPT Smart Assistant (with Home Assistant Integration)

Turn your crib into a smart castle with a slick, locally-powered AI assistant—leveraging LLaMA for smooth convos and GPT-4o for heavy-duty tasks. Seamlessly control your smart home via Home Assistant and keep interactions natural and context-aware. Ready to flex your smart-home hustle? Let's get it.

---

## 🛠️ Tech Stack

* **Local LLaMA 3** (via Ollama) for quick, local responses.
* **GPT-4o** for complex queries (code, research, multi-step logic).
* **FastAPI** backend for blazing-fast REST endpoints.
* **Home Assistant** for ultimate home automation.
* **Docker** for easy scalability and deployment.

## 🚀 Quick Start

### 📥 1. Setup Ollama & LLaMA 3

* Install Ollama CLI and pull LLaMA 3.

```bash
ollama pull llama3
ollama run llama3
```

### 🖥️ 2. Backend Installation

Clone the repo and install dependencies:

```bash
git clone https://github.com/your-org/GesahniV2.git && cd GesahniV2
pip install -r requirements.txt
cp .env.example .env
```

Alternatively, a convenience script is provided:

```bash
bash app/setup.sh
```

### 🔑 3. Configure Environment

GesahniV2 uses a multi-environment configuration system to eliminate configuration drift. Choose your environment and configure it:

#### Quick Start (Development)

```bash
# Switch to development environment
./scripts/switch_env.sh dev

# Edit .env to add your API keys and secrets
nano .env
```

#### Environment Options

- **Development** (`env.dev`): Local development with HTTP and relaxed security
- **Staging** (`env.staging`): Test environment with HTTPS and production-like security
- **Production** (`env.prod`): Production environment with HTTPS and strict security

#### Environment-Specific Variables

Each environment configures these key variables:

| Variable | Dev | Staging | Production | Purpose |
|----------|-----|---------|------------|---------|
| `APP_URL` | `http://localhost:3000` | `https://staging.gesahni.com` | `https://app.gesahni.com` | Frontend base URL |
| `API_URL` | `http://localhost:8000` | `https://api-staging.gesahni.com` | `https://api.gesahni.com` | Backend base URL |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | `https://staging.gesahni.com` | `https://app.gesahni.com` | Allowed frontend origins |
| `COOKIE_SECURE` | `0` | `1` | `1` | Require HTTPS for cookies |
| `COOKIE_SAMESITE` | `lax` | `lax` | `strict` | Cookie SameSite policy |
| `NEXT_PUBLIC_HEADER_AUTH_MODE` | `0` | `0` | `0` | Auth mode (0=cookie, 1=header) |

#### Required Configuration

After switching environments, you must configure:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | OpenAI authentication for GPT & Whisper |
| `JWT_SECRET` | Yes | JWT secret for protected endpoints |
| `HOME_ASSISTANT_TOKEN` | Yes* | Home Assistant long-lived token |
| `OPENWEATHER_API_KEY` | Yes* | Weather and forecast lookups |
| `SPOTIFY_CLIENT_ID` | No* | Spotify integration |
| `SPOTIFY_CLIENT_SECRET` | No* | Spotify integration |

*Required only if using those features.

#### Manual Configuration

If you prefer manual setup:

```bash
# Copy the appropriate environment file
cp env.dev .env      # For development
cp env.staging .env  # For staging
cp env.prod .env     # For production

# Edit .env to add your secrets and API keys
nano .env
```

#### Environment Loading

The system loads environment variables in this order (highest precedence first):
1. `.env` - Your local configuration (overrides everything)
2. `env.example` - Default values (fills missing keys only)
3. `env.dev`/`env.staging`/`env.prod` - Environment-specific defaults

For complete documentation, see [Environment Configuration](docs/environment_configuration.md).

### 🌐 4. Launch Backend

Start FastAPI:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or use environment variables:

```bash
HOST=127.0.0.1 PORT=8000 uvicorn app.main:app
```

### 📦 Frontend

The single web UI lives in `frontend/` (Next.js 15). A previously experimental `web/` app has been removed to keep things lean.

```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

### ⚙️ Startup & Initialization (developer reference)

This project centralizes application boot-time logic in `app/startup/` so the
FastAPI application can rely on an environment-first, test-friendly startup
sequence. Key points:

- `app/startup/config.py` — Detects the runtime profile (`dev`, `prod`, `ci`) and
  returns a `StartupProfile` describing which components to run and in which
  order.
- `app/startup/components.py` — Concrete, small async initializers (DB, token
  schema, OpenAI health, vector store, LLaMA, Home Assistant, memory, scheduler).
  Each initializer is tolerant of missing configuration and logs warnings
  instead of raising for optional externals.
- `app/startup/vendor.py` — Lightweight vendor health checks (OpenAI, Ollama)
  gated by `STARTUP_VENDOR_PINGS` and configurable timeouts.
- `app/startup/__init__.py` — Exports a `lifespan` asynccontextmanager used by
  FastAPI (`lifespan=app.startup.lifespan`) to orchestrate startup and shutdown.

Developer tips:

- Run the acceptance checks after editing startup logic:
  ```bash
  python -c "import importlib; importlib.import_module('app.main')"
  uvicorn app.main:app --reload
  CI=1 uvicorn app.main:app --reload
  curl -s localhost:8000/health | jq .
  curl -s localhost:8000/v1/status | jq .
  ```
- Keep initializers small and idempotent: they may be called in tests and in
  production; prefer logging and non-fatal failures for optional dependencies
  (Home Assistant, Ollama).
- Document any new startup component in `app/startup/components.py` and list
  it in `app/startup/config.py` if it should be part of profiles.


### 🎥 Record a Session

Record interaction sessions for later review:

```bash
python record_session.py --duration 5 --output ./sessions
```

### 📊 Metrics & Monitoring

* The backend exposes Prometheus metrics at `http://127.0.0.1:8000/metrics`.
* Metrics include request volume, latency histograms, and request cost.
* Import `grafana_dashboard.json` into Grafana for a sample dashboard with latency,
  cache hit rate, cost, and request volume panels.
* Additional metrics:
  - `dependency_latency_seconds{dependency,operation}`: External dependencies (e.g., qdrant, openai) latency.
  - `embedding_latency_seconds{backend}`: Embedding backend latency.
  - `vector_op_latency_seconds{operation}`: Vector store operations latency.

## 🔐 Authentication

User accounts are stored in a SQLite database (`users.db` by default, override
with `USERS_DB`). Authenticate by POSTing to `/login` with a JSON body
containing `username` and `password`. A successful login returns both an access
token and a refresh token. Access tokens embed the user ID in the `sub` claim
and expire after `JWT_EXPIRE_MINUTES` (default 30 minutes); refresh tokens
expire after `JWT_REFRESH_EXPIRE_MINUTES` (default 1440 minutes).

```bash
curl -X POST 127.0.0.1:8000/login \
     -H "Content-Type: application/json" \
     -d '{"username":"alice","password":"wonderland"}'
```

Use the refresh token to obtain a new pair of tokens by POSTing to `/refresh`:

```bash
curl -X POST 127.0.0.1:8000/refresh \
     -H "Content-Type: application/json" \
     -d '{"refresh_token":"<token>"}'
```

To explicitly revoke a token, call `/logout` with the token in the Authorization
header. Revoked token IDs are stored in memory and cannot be reused.

```bash
curl -X POST 127.0.0.1:8000/logout -H "Authorization: Bearer <refresh_token>"
```

### Spotify OAuth Runbook

Quick flow:

1. User clicks Connect on the Settings page (authenticated) → frontend calls `GET /v1/spotify/connect`.
2. Backend creates PKCE challenge and signed `state`, stores oauth_tx, and responds with `authorize_url`.
3. Frontend redirects user to Spotify authorize URL; user consents.
4. Spotify redirects to `/v1/spotify/callback?code=...&state=...`.
5. Backend validates HMAC state, ensures oauth_tx is PENDING, exchanges code using stored code_verifier, upserts tokens, issues auth cookies, marks oauth_tx CONSUMMATED, and redirects to `/settings/integrations?spotify=connected`.

Troubleshooting:

| Symptom | Likely cause | Fix |
|---|---|---|
| Cookies not present after redirect | Running on `http://localhost` but cookies marked `Secure` | Ensure `COOKIE_SECURE=0` for dev or use HTTPS; cookie_samesite must be `Lax` for localhost HTTP |
| Redirect mismatch error | `SPOTIFY_REDIRECT_URI` doesn't match Spotify app settings | Update Spotify app redirect URI to match `SPOTIFY_REDIRECT_URI` env |
| State invalid | State signature expired or mismatched | Ensure `JWT_STATE_SECRET` is same across instances and clocks are synced; check oauth_tx store TTL |

## Disconnecting Spotify

Use the Disconnect endpoint to revoke stored Spotify tokens and remove Spotify from connected providers on next auth mint:

```bash
curl -X DELETE http://127.0.0.1:8000/v1/spotify/disconnect -H "Authorization: Bearer <access_token>"
```

This marks Spotify tokens as invalid in the DB and updates `last_refresh_at` to signal revocation.

### Clerk (JWT) backend verification

Enable JWT verification against Clerk JWKS for HTTP + WS:

```env
# One of the following is required
CLERK_ISSUER=https://<tenant>.clerk.accounts.dev
# or provide JWKS directly
# CLERK_JWKS_URL=https://<tenant>.clerk.accounts.dev/.well-known/jwks.json

# Optional audience enforcement (recommended)
CLERK_AUDIENCE=<your-publishable-key-or-aud>
```

- Reusable dependency: `app/deps/clerk_auth.py` → `require_user()` validates the Bearer token, attaches
  `request.state.jwt_payload`, `request.state.user_id`, `request.state.email`, and `request.state.roles`.
- WS handshake guard: `require_user_ws()` closes with code 1008 and a clear reason when invalid.
- Example protected route: `GET /v1/auth/clerk/protected` (200 with valid token; 401 otherwise).

### Roles and gates

- Roles can be set in Clerk via Organization roles or custom user metadata. Ensure a `roles` claim appears in the session JWT (array or space/comma-separated string). You can mirror roles from scopes if you prefer (`admin` from `admin:write`, `caregiver` from `care:caregiver`, `resident` from `care:resident`).
- Dependency helper: `require_roles(["admin"])`, `require_roles(["caregiver"])`, `require_roles(["resident"])` in `app/deps/roles.py`.
- Behavior: missing/invalid token → 401; authenticated without required role → 403.

### Device/TV pairing (scoped device token)

Endpoints:
- `POST /v1/devices/pair/start` (auth required): returns `{ code, expires_in }`. Optionally send `X-Device-Label` header (e.g., `tv-livingroom`).
- `POST /v1/devices/pair/complete` (device): body `{ code }` → returns `{ access_token, token_type, expires_in }`. Token is HS256 JWT with `scope: "care:resident"`, `roles: ["resident"]`, `type: "device"`.
- `POST /v1/devices/{id}/revoke` (owner): revokes a device token. Body may include `{ jti }` or header `X-Device-Token-ID`.

Simulate pairing:
1) User (browser): `curl -H "Authorization: Bearer <user_jwt>" -H "X-Device-Label: tv-livingroom" -X POST http://127.0.0.1:8000/v1/devices/pair/start`
2) TV/device: `curl -X POST http://127.0.0.1:8000/v1/devices/pair/complete -H 'Content-Type: application/json' -d '{"code":"<code>"}'`
3) TV stores `access_token` and uses it as Bearer for resident‑scoped endpoints (e.g., `/v1/care/*`). Admin endpoints remain 403.

Revocation:
- Owner can call `POST /v1/devices/{id}/revoke` with `Authorization: Bearer <owner_jwt>` and `{ "jti": "..." }` to revoke immediately.

Storage:
- Pairing codes and active device tokens are stored in Redis (keys prefixed `pair:code:*` and `device:token:*`). TTLs: `DEVICE_PAIR_CODE_TTL_S` (default 300s), `DEVICE_TOKEN_TTL_S` (default 30d).

## 🎯 Endpoints

* `/ask`: Send your prompt here.
  - Canonical body: `{ prompt: string | Message[], model?: string, stream?: boolean }`
  - Liberal inputs accepted and normalized internally: `message`, `text`, `query`, `q`, `input.prompt|text|message`, `messages: [{ role, content }]`
  - Provider adapters:
    - Chat models (e.g. `gpt-4o`): string prompt is wrapped as one user message; arrays are passed as-is.
    - Completion models (e.g. `llama3` via Ollama): messages are joined into a single text prompt.
  - Streaming behavior: set `stream: true` to force SSE; else uses `Accept: text/event-stream`.
  - Errors: invalid inputs return 4xx with clear `detail`; upstream 4xx are preserved.
* `/upload`: upload audio for transcription.
* `/sessions`: list captured sessions.
* `/sessions/{id}/transcribe`: queue transcription for a session.
* `/sessions/{id}/summarize`: queue summary generation.
* `/transcribe/{session_id}` (POST/GET): start or fetch transcription.
* `WS /transcribe`: stream audio for live transcription.
* `/ha/entities`, `/ha/service`, `/ha/resolve`: Home Assistant helpers.
* `/health` and `/status`: service status info.
* `/healthz`: unauthenticated health probe.
* `/config`: view config.
* `/intent-test`: debug your prompt intent.

Note: all endpoints are also available under the `/v1` prefix.

## Skills

Built-in skills handle common tasks before hitting the language model. The first
skill that matches your prompt runs:

```bash
curl -X POST 127.0.0.1:8000/ask -d '{"prompt":"turn off kitchen lights"}'
# → OK—kitchen lights off.
```

## 🤖 Smart Routing Logic

* **Home Assistant**: Automation and device commands.
* **LLaMA**: Casual conversation, quick info.
* **GPT-4o**: Complex questions, coding, deep research.

## 🧠 Advanced Features

* **Context-Aware Memory**: Remembers recent prompts.
* **Dynamic Entity Resolution**: Smartly matches your commands to HA entities.
* **Robust Fail-safes**: Seamless fallbacks (LLaMA → GPT, graceful HA errors).
* **Proactive Engine v1**: Presence/webhook inputs, curiosity loop, APScheduler self‑tasks (e.g., unlock notifications and auto‑lock), hourly profile persistence.
* **Security & Policy**: Per‑route scopes (`/admin/*`, `/ha/*`), nonce guard for state changes, signed webhooks with rotation helpers, deny‑list moderation on HA actions, dual‑bucket rate limits with Retry‑After.

### Distributed rate limiting

- Default backend: in‑memory (process‑local)
- Optional backend: Redis (distributed across instances)

Enable Redis:

```bash
cp docker-compose.redis.yml docker-compose.override.yml
docker compose up -d redis

export RATE_LIMIT_BACKEND=redis
export REDIS_URL=redis://localhost:6379/0
# optional
export RATE_LIMIT_BYPASS_SCOPES="admin support"
export DAILY_REQUEST_CAP=0
```

Health:

```bash
curl -s http://127.0.0.1:8000/rate_limit_status
```

Per‑route overrides example:

```python
from fastapi import Depends
from app.security import rate_limit_with, scope_rate_limit

@router.get("/burst-heavy", dependencies=[Depends(rate_limit_with(burst_limit=3))])
async def burst_heavy():
    return {"ok": True}

@router.get("/admin/critical", dependencies=[Depends(scope_rate_limit("admin", long_limit=30, burst_limit=5))])
async def admin_critical():
    return {"ok": True}
```

Daily caps and bypass scopes:

- `DAILY_REQUEST_CAP`: per-user daily cap across HTTP/WS (UTC midnight reset). `0` disables.
- `RATE_LIMIT_BYPASS_SCOPES`: space-separated scopes that bypass all limits.

### Embedding Flow

Memories and provenance tags rely on embeddings to gauge similarity:

1. `EMBEDDING_BACKEND` chooses between OpenAI and local LLaMA models using `EMBED_MODEL` or `LLAMA_EMBEDDINGS_MODEL`.
2. When a reply is generated, `_annotate_provenance` embeds each memory chunk and every response line via `embed_sync`.
3. Cosine similarity compares response lines to stored memories. Lines with similarity ≥0.60 gain a `[#chunk:ID]` tag.
4. These tags make it clear which memories influenced an answer and power the semantic cache.

## 📈 Future Enhancements

* Voice Activation (Porcupine/Vosk)
* Mobile App (React Native/PWA)
* Custom Skills (Calendar, Weather, Music)
* Advanced Notifications (Pushover/Shortcuts)
* Personality Modules (Customize assistant's tone)

---

### 🧪 Tests and Load

Run the full test suite:

```bash
pytest -q
```

Smoke (golden flow) tests only:

```bash
pytest -q tests/smoke
```

Run k6 load test (with basic SLO thresholds):

```bash
k6 run scripts/k6_load_test.js -e BASE_URL=http://127.0.0.1:8000
```

Locust:

```bash
locust -f locustfile.py --host=http://127.0.0.1:8000
```

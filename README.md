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
Set environment variables as needed:

| Var | Default | Required | Purpose |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | – | yes | OpenAI auth for GPT & Whisper |
| `OPENAI_MODEL` | `gpt-4o` | no | Default GPT model |
| `OPENAI_TRANSCRIBE_MODEL` | `whisper-1` | no | Async Whisper model |
| `WHISPER_MODEL` | `whisper-1` | no | Sync Whisper model |
| `ALLOWED_GPT_MODELS` | `gpt-4o,gpt-4,gpt-3.5-turbo` | no | Valid `/ask` model overrides |
| `ALLOWED_LLAMA_MODELS` | `llama3:latest,llama3` | no | Valid `/ask` LLaMA overrides |
| `DEBUG` | – | no | Enable extra prompt debug info |
| `DEBUG_MODEL_ROUTING` | – | no | Log model path without external calls |
| `LOG_LEVEL` | `INFO` | no | Logging verbosity |
| `FOLLOW_UPS_FILE` | `data/follow_ups.json` | no | Stored follow-up reminders |
| `OLLAMA_URL` | `http://localhost:11434` | no | Ollama base URL |
| `OLLAMA_MODEL` | `llama3:latest` | no | LLaMA model name |
| `OLLAMA_FORCE_IPV6` | – | no | Force IPv6 for Ollama requests |
| `LLAMA_MAX_STREAMS` | `2` | no | Max concurrent LLaMA streams |
| `JWT_SECRET` | `change-me` | no | JWT secret for protected endpoints |
| `JWT_EXPIRE_MINUTES` | `30` | no | Access token lifetime |
| `JWT_REFRESH_EXPIRE_MINUTES` | `1440` | no | Refresh token lifetime |
| `RATE_LIMIT_PER_MIN` | `60` | no | Requests per minute per IP |
| `API_TOKEN` | – | no | Static token for legacy clients |
| `REDIS_URL` | `redis://localhost:6379/0` | no | RQ queue for async tasks (optional; falls back to threads) |
| `HISTORY_FILE` | `data/history.jsonl` | no | Request history log |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | no | Allowed web origins |
| `PORT` | `8000` | no | Server port when running `python app/main.py` |
| `SESSIONS_DIR` | `sessions/` | no | Base directory for session media |
| `ADMIN_TOKEN` | – | no | Required to read `/config` |
| `HOME_ASSISTANT_URL` | `http://localhost:8123` | no | Home Assistant base URL |
| `HOME_ASSISTANT_TOKEN` | – | yes | HA long-lived token |
| `INTENT_THRESHOLD` | `0.7` | no | Intent confidence cutoff |
| `LLAMA_EMBEDDINGS_MODEL` | – | yes* | Path to GGUF when using llama embeddings |
| `EMBED_MODEL` | `text-embedding-3-small` | no | OpenAI embedding model |
| `EMBEDDING_BACKEND` | `openai` | no | Embedding provider (`openai` or `llama`) |
| `ROUTER_RULES_PATH` | `router_rules.yaml` | no | Path to deterministic router rules |
| `TRANSLATE_URL` | `http://localhost:5000` | no | Translation microservice |
| `OPENWEATHER_API_KEY` | – | yes | Weather and forecast lookups |
| `CITY_NAME` | `Detroit,US` | no | Default weather city |
| `NOTES_DB` | `notes.db` | no | SQLite file for notes skill |
| `CALENDAR_FILE` | `data/calendar.json` | no | Calendar events source |
| `MAX_UPLOAD_BYTES` | `10485760` | no | Max upload size for session media |
| `SIM_THRESHOLD` | `0.24` | no | Vector similarity cutoff |
| `MEM_TOP_K` | `3` | no | Memories returned from vector store |
| `DISABLE_QA_CACHE` | `false` | no | Skip semantic cache when set |
| `VECTOR_STORE` | `chroma` | no | Vector store backend |
| `CHROMA_PATH` | `.chroma_data` | no | ChromaDB storage directory |
| `RAGFLOW_URL` | `http://localhost:8001` | no | Base URL for RAGFlow server |
| `RAGFLOW_COLLECTION` | `demo` | no | Default RAGFlow collection name |
| `USERS_DB` | `users.db` | no | SQLite path for auth users |

*Required only when `EMBEDDING_BACKEND=llama`.

Set `GPT_SYSTEM_PROMPT` to tweak the assistant's default persona. For example:

```bash
export GPT_SYSTEM_PROMPT="You are a pirate who talks like a pirate."
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 🌐 4. Launch Backend

Start FastAPI:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 📦 Docker

This repository does not currently ship a Dockerfile. If you add one, a typical workflow is:

```bash
docker build -t gesahni .
docker run -d -p 8000:8000 --env-file .env gesahni
```

### 🎥 Record a Session

Record interaction sessions for later review:

```bash
python record_session.py --duration 5 --output ./sessions
```

### 📊 Metrics & Monitoring

* The backend exposes Prometheus metrics at `http://localhost:8000/metrics`.
* Metrics include request volume, latency histograms, and request cost.
* Import `grafana_dashboard.json` into Grafana for a sample dashboard with latency,
  cache hit rate, cost, and request volume panels.

## 🔐 Authentication

User accounts are stored in a SQLite database (`users.db` by default, override
with `USERS_DB`). Authenticate by POSTing to `/login` with a JSON body
containing `username` and `password`. A successful login returns both an access
token and a refresh token. Access tokens embed the user ID in the `sub` claim
and expire after `JWT_EXPIRE_MINUTES` (default 30 minutes); refresh tokens
expire after `JWT_REFRESH_EXPIRE_MINUTES` (default 1440 minutes).

```bash
curl -X POST localhost:8000/login \
     -H "Content-Type: application/json" \
     -d '{"username":"alice","password":"wonderland"}'
```

Use the refresh token to obtain a new pair of tokens by POSTing to `/refresh`:

```bash
curl -X POST localhost:8000/refresh \
     -H "Content-Type: application/json" \
     -d '{"refresh_token":"<token>"}'
```

To explicitly revoke a token, call `/logout` with the token in the Authorization
header. Revoked token IDs are stored in memory and cannot be reused.

```bash
curl -X POST localhost:8000/logout -H "Authorization: Bearer <refresh_token>"
```

## 🎯 Endpoints

* `/ask`: Send your prompt here.
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
* Google integration endpoints such as `/google/auth/url`, `/google/oauth/callback`, `/google/gmail/send`, and `/google/calendar/create` require an authenticated user session. OAuth credentials are stored per user.

Note: all endpoints are also available under the `/v1` prefix.

## Skills

Built-in skills handle common tasks before hitting the language model. The first
skill that matches your prompt runs:

```bash
curl -X POST localhost:8000/ask -d '{"prompt":"turn off kitchen lights"}'
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

### 🛟 Troubleshooting & Logs

* Check logs at `/config` endpoint.
* Detailed error logs saved locally.

### 🗑️ Invalidate Cached Answers

Remove a stored response from the semantic cache using the CLI:

```bash
python -m app.vector_store invalidate "your original prompt"
```

## Event Log

Each `/ask` request writes a JSON object to `data/history.jsonl` capturing core
metadata and timing. New fields include `session_id`, `latency_ms`, `status` and
token usage. Missing fields default to `null`.

```json
{
  "req_id": "abc123",
  "session_id": "s-42",
  "prompt": "turn on hallway light",
  "engine_used": "LightsSkill",
  "response": "Done.",
  "latency_ms": 120,
  "status": "OK"
}
```

---

Made by the King, for the King. Let's run it! 🚀🔥

### Contributing
See `CONTRIBUTING.md` for development workflow, testing, and PR guidelines.

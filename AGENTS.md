## Project One-Liner
GesahniV2 is a FastAPI-based assistant that blends local LLaMA models, OpenAI GPT, and
Home Assistant to answer questions and automate your home.

## Directory Cheat Sheet
| Path | Purpose |
| --- | --- |
| `app/` | Backend services, skills, and routing logic |
| `frontend/` | Next.js web UI for interacting with the assistant (single UI; legacy `web/` removed) |
| `tests/` | Pytest suite validating routing, skills, and utilities |
| `data/` | History log, follow-up storage, sample calendar |
| `sessions/` | Captured audio/video sessions and metadata |
| `bench/` | Benchmark helpers for embeddings |

## Core Agents / Modules
| Agent | Location | Entrypoint | Purpose |
| --- | --- | --- | --- |
| RouterAgent | `app/router.py` | `route_prompt` | Decide between skills, Home Assistant, LLaMA, or GPT. |
| DeterministicRouter | `app/model_router.py` | `route_text`, `run_with_self_check` | Deterministic routing with YAML‑tuned thresholds and self‑check escalation. |
| LLaMAAgent | `app/llama_integration.py` | `ask_llama` | Query local Ollama with retries; env: `OLLAMA_URL`, `OLLAMA_MODEL`. |
| GPTAgent | `app/gpt_client.py` | `ask_gpt` | Call OpenAI chat API; env: `OPENAI_API_KEY`, `OPENAI_MODEL`. |
| HomeAssistantAgent | `app/home_assistant.py` | `handle_command` | Parse on/off commands and call HA REST API. |
| IntentAgent | `app/intent_detector.py` | `detect_intent` | Heuristic categorization of prompts. |
| TranscriptionAgent | `app/transcription.py` | `transcribe_file` | Async Whisper transcription. |
| SessionManager | `app/session_manager.py` | `start_session` | Handle media uploads and tagging. |
| SecurityGuard | `app/security.py` | `verify_token` | Bearer token auth and per-IP rate limiting. |
| StatusReporter | `app/status.py` | `router` | Expose health, config, and metrics endpoints. |

## HTTP Endpoints
Method | Path | Handler
--- | --- | ---
GET | `/me` | Authenticated user info and stats (also under `/v1/me`)
POST | `/ask` | Route prompt through skills and LLMs (also under `/v1/ask`)
POST | `/upload` | Save raw audio upload
POST | `/capture/start` | Begin capture session
POST | `/capture/save` | Finalize capture, store media
POST | `/capture/tags` | Queue tag extraction
GET | `/capture/status/{id}` | Fetch session metadata
GET | `/search/sessions` | Search stored sessions
GET | `/sessions` | List sessions by status
POST | `/sessions/{id}/transcribe` | Queue session transcription
POST | `/sessions/{id}/summarize` | Queue session summary
WS | `/transcribe` | Stream audio chunks for live transcription
POST | `/intent-test` | Echo prompt for intent debugging
GET | `/ha/entities` | Dump Home Assistant states
POST | `/ha/service` | Call arbitrary HA service
GET | `/ha/resolve` | Resolve friendly name to entity ID
POST | `/transcribe/{id}` | Transcribe saved session
GET | `/transcribe/{id}` | Retrieve transcript
GET | `/health` | Basic heartbeat
GET | `/healthz` | Unauthenticated probe (for orchestration)
GET | `/metrics` | Prometheus metrics (enabled when `PROMETHEUS_ENABLED=1`)
POST | `/v1/music` | Music control: play|pause|next|previous|volume
POST | `/v1/vibe` | Set/update vibe preset (name, energy, tempo, explicit)
GET | `/v1/state` | Current music state (vibe, volume, playing, track)
GET | `/v1/queue` | Current queue
GET | `/v1/recommendations` | Recommendations seeded by vibe + last track
GET | `/v1/music/devices` | List provider devices (Spotify)
POST | `/v1/music/device` | Transfer playback to a device
WS | `/v1/ws/music` | Broadcast: `music.state`, `music.queue.updated`
GET | `/config` | Dump environment (requires `ADMIN_TOKEN`)
GET | `/ha_status` | Home Assistant health check
GET | `/llama_status` | Ollama health check
GET | `/status` | Aggregate service health
GET | `/metrics` | Prometheus metrics

## Skills Catalog
Skills are tried in the order defined in `app/skills/__init__.py`; first match wins.
| Skill | name() | Purpose |
| --- | --- | --- |
| SmalltalkSkill | `smalltalk` | Friendly greetings and persona tags |
| ClockSkill | `clock` | Report time, date, or start a countdown |
| WorldClockSkill | `world_clock` | Show time in major cities |
| WeatherSkill | `weather` | Current weather via OpenWeather |
| ForecastSkill | `forecast` | 3-day forecast from OpenWeather |
| ReminderSkill | `reminder` | Schedule one-off or recurring reminders |
| TimerSkill | `timer` | Start, cancel, or query timers |
| MathSkill | `math` | Basic arithmetic and percentages |
| UnitConversionSkill | `unit_conversion` | Convert between units (C↔F, km↔mi, etc.) |
| CurrencySkill | `currency` | Convert currency amounts |
| CalendarSkill | `calendar` | Show today's or upcoming events |
| TeachSkill | `teach` | Map nicknames to Home Assistant entities |
| EntitiesSkill | `entities` | List HA entities, lights, or switches |
| SceneSkill | `scene` | Activate a Home Assistant scene |
| ScriptSkill | `script` | Run a Home Assistant script |
| CoverSkill | `cover` | Open or close covers (blinds, garage) |
| FanSkill | `fan` | Turn fans or air purifiers on/off |
| NotifySkill | `notify` | Send a phone notification |
| SearchSkill | `search` | DuckDuckGo instant answer search |
| TranslateSkill | `translate` | Translate text or detect language |
| NewsSkill | `news` | Top headlines from Hacker News RSS |
| JokeSkill | `joke` | Fetch a random joke |
| DictionarySkill | `dictionary` | Define words or list synonyms |
| RecipeSkill | `recipe` | Pull recipe ingredients and steps |
| LightsSkill | `lights` | Control lights and brightness |
| DoorLockSkill | `door_lock` | Lock, unlock, or query doors |
| MusicSkill | `music` | Play/pause music or artists via HA |
| RokuSkill | `roku` | Launch Roku apps |
| ClimateSkill | `climate` | Set or report thermostat temperature |
| VacuumSkill | `vacuum` | Start or stop the vacuum |
| NotesSkill | `notes` | Add, list, show, or delete notes |
| StatusSkill | `status` | Report backend, HA, and LLaMA health |

## Environment & Secrets
| Var | Default | Required | Purpose |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | – | yes | OpenAI auth for GPT & Whisper |
| `OPENAI_MODEL` | `gpt-4o` | no | Default GPT model |
| `OPENAI_TRANSCRIBE_MODEL` | `whisper-1` | no | Async Whisper model |
| `WHISPER_MODEL` | `whisper-1` | no | Sync Whisper model |
| `ALLOWED_GPT_MODELS` | `gpt-4o,gpt-4,gpt-3.5-turbo` | no | Valid `/ask` model overrides |
| `DEBUG_MODEL_ROUTING` | – | no | Log model path without external calls |
| `LOG_LEVEL` | `INFO` | no | Logging verbosity |
| `FOLLOW_UPS_FILE` | `data/follow_ups.json` | no | Stored follow-up reminders |
| `OLLAMA_URL` | `http://localhost:11434` | no | Ollama base URL |
| `OLLAMA_MODEL` | `llama3:latest` | no | LLaMA model name |
| `LLAMA_MAX_STREAMS` | `2` | no | Max concurrent Ollama requests |
| `ALLOWED_LLAMA_MODELS` | `llama3:latest,llama3` | no | Valid `/ask` LLaMA overrides |
| `JWT_SECRET` | – | no | JWT secret for protected endpoints |
| `API_TOKEN` | – | no | Static token for legacy clients |
| `JWT_EXPIRE_MINUTES` | `30` | no | Access token expiry minutes |
| `JWT_REFRESH_EXPIRE_MINUTES` | `1440` | no | Refresh token expiry minutes |
| `RATE_LIMIT_PER_MIN` | `60` | no | Requests per minute per IP |
| `REDIS_URL` | `redis://localhost:6379/0` | no | RQ queue for async tasks (optional; falls back to threads) |
| `HISTORY_FILE` | `data/history.jsonl` | no | Request history log |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | no | Allowed web origins (exactly localhost, not 127.0.0.1) |
| `CORS_ALLOW_CREDENTIALS` | `true` | no | Allow credentials (cookies/tokens) |
| `HOST` | `localhost` | no | Server host when running `python app.main:app` |
| `PORT` | `8000` | no | Server port when running `python app.main.py` |
| `SESSIONS_DIR` | `sessions/` | no | Base directory for session media |
| `ADMIN_TOKEN` | – | no | Required to read `/config` |
| `INTENT_THRESHOLD` | `0.7` | no | Intent classification cutoff |
| `SBERT_MODEL` | `sentence-transformers/paraphrase-MiniLM-L3-v2` | no | Intent detection model |
| `MODEL_ROUTER_HEAVY_WORDS` | `30` | no | Word count to trigger heavy model |
| `MODEL_ROUTER_HEAVY_TOKENS` | `1000` | no | Token count to trigger heavy model |
| `SIM_THRESHOLD` | `0.24` | no | Vector similarity cutoff |
| `HOME_ASSISTANT_URL` | `http://localhost:8123` | no | Home Assistant base URL |
| `HOME_ASSISTANT_TOKEN` | – | yes | HA long-lived token |
| `LLAMA_EMBEDDINGS_MODEL` | – | yes* | Path to GGUF when using llama embeddings |
| `EMBED_MODEL` | `text-embedding-3-small` | no | OpenAI embedding model |
| `EMBEDDING_BACKEND` | `openai` | no | Embedding provider (`openai` or `llama`) |
| `DETERMINISTIC_ROUTER` | `0` | no | Enable deterministic router (`1` to enable) |
| `ROUTER_RULES_PATH` | `router_rules.yaml` | no | Path to YAML rules for deterministic router |
| `MEM_TOP_K` | `3` | no | Max memories returned from vector store |
| `CHROMA_PATH` | `.chroma_data` | no | ChromaDB storage directory |
| `RAGFLOW_URL` | `http://localhost:8001` | no | Base URL for RAGFlow server |
| `RAGFLOW_COLLECTION` | `demo` | no | Default RAGFlow collection name |
| `TRANSLATE_URL` | `http://localhost:5000` | no | Translation microservice |
| `OPENWEATHER_API_KEY` | – | yes | Weather and forecast lookups |
| `CITY_NAME` | `Detroit,US` | no | Default weather city |
| `NOTES_DB` | `notes.db` | no | SQLite file for notes skill |
| `CALENDAR_FILE` | `data/calendar.json` | no | Calendar events source |
| `MAX_UPLOAD_BYTES` | `10485760` | no | Max upload size for session media |
| `DISABLE_QA_CACHE` | `false` | no | Skip semantic cache when set |
| `VECTOR_STORE` | `chroma` | no | Vector store backend (`memory`, `chroma`, `qdrant`, `dual`, `cloud`) |
| `STRICT_VECTOR_STORE` | `0` | no | Fail hard on vector store init errors when `1` |
| `PROMETHEUS_ENABLED` | `1` | no | Expose `/metrics` endpoint when enabled |
| `OTEL_ENABLED` | `1` | no | Enable OpenTelemetry traces (exporter optional) |

*Required only when `EMBEDDING_BACKEND=llama`.

## Setup / Local Dev Quick-Start
1. **Install deps**
   ```bash
   pip install -r requirements.txt
   ```
2. **Run LLaMA (Ollama)**
   ```bash
   ollama pull llama3
   ollama run llama3
   ```
3. **Start backend**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
4. **Start frontend**
   ```bash
   cd frontend && npm run dev
   ```

## Testing & Validation
See `CONTRIBUTING.md` for the full development workflow, including tests and linting.

### Smoke tests (golden flows)
```bash
pytest -q tests/smoke
```

### Load testing
- k6 (with basic SLO thresholds):
```bash
k6 run scripts/k6_load_test.js -e BASE_URL=http://127.0.0.1:8000
```
- Locust:
```bash
locust -f locustfile.py --host=http://127.0.0.1:8000
```

## Model Routing Rules
- Accept `model_override` from frontend POST body.
- Route `"llama*"` models to `ask_llama()`, `"gpt*"` models to `ask_gpt()`.
- If OpenAI dependency is missing, fallback to LLaMA instead of failing.

## Skill-Authoring Checklist
- Copy `app/skills/example_skill.py` style into a new `<name>_skill.py`.
- Implement a `Skill` subclass with `PATTERNS` and `run()`.
- Import and append the class in `app/skills/__init__.py` to set execution order.
- Add tests under `tests/` covering positive and negative cases.
- Run formatting, lint, and test commands above.

## Contributing
Please read `CONTRIBUTING.md` for contribution guidelines and the PR checklist.

## Observability & Metrics
- Request metrics: `app_request_total`, `app_request_latency_seconds`, `app_request_cost_usd`
- Routing: `router_decision_total`
- Model latency: `model_latency_seconds`
- New dependency/vector metrics:
  - `dependency_latency_seconds{dependency,operation}` (e.g., qdrant upsert/search)
  - `embedding_latency_seconds{backend}` (openai|llama|stub)
  - `vector_op_latency_seconds{operation}` (upsert|search|scroll|delete)
- Rate limit: `rate_limit_allow_total`, `rate_limit_block_total`; responses include `X-RateLimit-*` headers.
- Tracing: `X-Request-ID` and `X-Trace-ID` response headers aid correlation; enable traces via `OTEL_ENABLED=1`.

## Request Flow
```mermaid
sequenceDiagram
  participant U as User
  participant A as /ask
  participant R as RouterAgent
  participant S as Skills
  participant H as Home Assistant
  participant L as LLaMA
  participant G as GPT
  U->>A: POST /ask
  A->>R: route_prompt
  R->>S: check_builtin_skills
  alt skill match
    S-->>R: response
  else
    R->>H: handle_command
    alt HA success
      H-->>R: result
    else
      R->>L: ask_llama
      alt LLaMA ok
        L-->>R: answer
      else
        R->>G: ask_gpt
        G-->>R: answer
      end
    end
  end
  R-->>U: final response

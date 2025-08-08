## Project One-Liner
GesahniV2 is a FastAPI-based assistant that blends local LLaMA models, OpenAI GPT, and
Home Assistant to answer questions and automate your home.

## Directory Cheat Sheet
| Path | Purpose |
| --- | --- |
| `app/` | Backend services, skills, and routing logic |
| `frontend/` | Next.js web UI for interacting with the assistant |
| `tests/` | Pytest suite validating routing, skills, and utilities |
| `data/` | History log, follow-up storage, sample calendar |
| `sessions/` | Captured audio/video sessions and metadata |
| `bench/` | Benchmark helpers for embeddings |

## Core Agents / Modules
| Agent | Location | Entrypoint | Purpose |
| --- | --- | --- | --- |
| RouterAgent | `app/router.py` | `route_prompt` | Decide between skills, Home Assistant, LLaMA, or GPT. |
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
POST | `/ask` | Route prompt through skills and LLMs
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
| `OLLAMA_URL` | – | yes | Ollama base URL |
| `OLLAMA_MODEL` | `llama3:latest` | no | LLaMA model name |
| `LLAMA_MAX_STREAMS` | `2` | no | Max concurrent Ollama requests |
| `ALLOWED_LLAMA_MODELS` | `llama3:latest,llama3` | no | Valid `/ask` LLaMA overrides |
| `JWT_SECRET` | – | no | JWT secret for protected endpoints |
| `API_TOKEN` | – | no | Static token for legacy clients |
| `JWT_EXPIRE_MINUTES` | `30` | no | Access token expiry minutes |
| `JWT_REFRESH_EXPIRE_MINUTES` | `1440` | no | Refresh token expiry minutes |
| `RATE_LIMIT_PER_MIN` | `60` | no | Requests per minute per IP |
| `REDIS_URL` | – | yes | RQ queue for async tasks |
| `HISTORY_FILE` | `data/history.jsonl` | no | Request history log |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | no | Allowed web origins |
| `PORT` | `8000` | no | Server port when running `python app/main.py` |
| `SESSIONS_DIR` | `sessions/` | no | Base directory for session media |
| `ADMIN_TOKEN` | – | no | Required to read `/config` |
| `INTENT_THRESHOLD` | `0.7` | no | Intent classification cutoff |
| `SBERT_MODEL` | `sentence-transformers/paraphrase-MiniLM-L3-v2` | no | Intent detection model |
| `MODEL_ROUTER_HEAVY_WORDS` | `30` | no | Word count to trigger heavy model |
| `MODEL_ROUTER_HEAVY_TOKENS` | `1000` | no | Token count to trigger heavy model |
| `SIM_THRESHOLD` | `0.90` | no | Vector similarity cutoff |
| `HOME_ASSISTANT_URL` | `http://localhost:8123` | no | Home Assistant base URL |
| `HOME_ASSISTANT_TOKEN` | – | yes | HA long-lived token |
| `LLAMA_EMBEDDINGS_MODEL` | – | yes* | Path to GGUF when using llama embeddings |
| `EMBED_MODEL` | `text-embedding-3-small` | no | OpenAI embedding model |
| `EMBEDDING_BACKEND` | `openai` | no | Embedding provider (`openai` or `llama`) |
| `TRANSLATE_URL` | `http://localhost:5000` | no | Translation microservice |
| `OPENWEATHER_API_KEY` | – | yes | Weather and forecast lookups |
| `CITY_NAME` | `Detroit,US` | no | Default weather city |
| `NOTES_DB` | `notes.db` | no | SQLite file for notes skill |
| `CALENDAR_FILE` | `data/calendar.json` | no | Calendar events source |
| `MAX_UPLOAD_BYTES` | `10485760` | no | Max upload size for session media |
| `DISABLE_QA_CACHE` | `false` | no | Skip semantic cache when set |
| `VECTOR_STORE` | `chroma` | no | Vector store backend |

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
   uvicorn app.main:app --reload
   ```
4. **Start frontend**
   ```bash
   cd frontend && npm run dev
   ```

## Testing & Validation
Run before committing:
```bash
pytest -q
ruff check .
black --check .
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

## Contribution / PR Template
```
### Problem
Explain the issue.

### Solution
Describe your change.

### Tests
`pytest -q`
`ruff check .`
`black --check .`

### Risk
Note any edge cases or follow-up work.
```

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

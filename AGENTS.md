# AGENTS.md

Welcome to the cast of GesahniV2—your personal AI ensemble that handles everything from local LLaMA chat to flicking on the hallway lights. Here’s who’s who and what they do.

---

## RouterAgent
**Location:** `app/router.py`  
**Entrypoint:** `async def route_prompt(prompt: str) -> str`

- **Purpose:**  
  Decide which backend “voice” answers your prompt: Home Assistant → GPT → LLaMA (with smart fallbacks and retries).
- **Trigger:**  
  Every incoming `/ask` request.
- **Logic:**  
  1. **HA first**: If `handle_command(prompt)` returns a non-`None` result, serve it.  
  2. **Complex?** If prompt >30 words or contains keywords (`code`, `research`, `analyze`, `explain`), try GPT → on error fallback to LLaMA.  
  3. **Else** use LLaMA → on error fallback to GPT.
- **Tools:**  
  - `ask_llama` (Ollama)  
  - `ask_gpt` (OpenAI)  
  - `handle_command` (Home Assistant)

---

## LLaMAAgent
**Location:** `app/llama_integration.py`
**Entrypoint:** `async def ask_llama(prompt: str, model: str | None = None) -> str`

- **Purpose:**  
  Handle local “LLaMA” conversations via your self‑hosted Ollama server.
- **Inputs:**  
  - `prompt`: plain text  
  - `model`: optional override (defaults to `OLLAMA_MODEL`)
- **Outputs:**  
  - Stripped response text from Ollama.
- **Tools:**  
  - `httpx.AsyncClient` → `POST {OLLAMA_URL}/api/generate`  
  - Env vars: `OLLAMA_URL`, `OLLAMA_MODEL`
- **Error Handling:**  
  Logs and re‑raises any exceptions for RouterAgent to catch.

---

## GPTagent
**Location:** `app/gpt_client.py`  
**Entrypoint:** `async def ask_gpt(prompt: str, model: str | None = None) -> str`

- **Purpose:**  
  Fallback and heavy‑lifting for complex prompts using OpenAI’s API.
- **Inputs:**  
  - `prompt`: user text  
  - `model`: optional override (defaults to `OPENAI_MODEL`)
- **Outputs:**  
  - First choice content from the chat completion response.
- **Tools:**  
  - `openai.AsyncOpenAI` client  
  - Env vars: `OPENAI_API_KEY`, `OPENAI_MODEL`
- **Error Handling:**  
  Logs and re‑raises to let RouterAgent handle fallbacks.

---

## HomeAssistantAgent
**Location:** `app/home_assistant.py`  
**Entrypoint:** `async def handle_command(prompt: str) -> Optional[str]`

- **Purpose:**  
  Parse “turn on/off `<entity>`” style prompts, resolve entity IDs, and call HA services.
- **Trigger:**  
  Prompts matching `^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$`.
- **Workflow:**  
  1. **_request:** Internal HTTP helper (GET/POST) to HA REST API.  
  2. **get_states:** Fetch all entities with `/api/states`.  
  3. **resolve_entity:** Match user-friendly name or partial entity_id → returns `domain.entity`.  
  4. **call_service:** Hit `/api/services/{domain}/{service}` with JSON data.  
  5. **turn_on/turn_off:** Convenience wrappers around `call_service`.  
- **Outputs:**  
  - Success strings: e.g. `Turned on light.kitchen`  
  - Errors: `Entity 'foo' not found` or `Failed to execute command`
- **Tools:**  
  - `httpx`, `re`, HA URL/Token env vars.

---

## IntentTestAgent
**Location:** `app/main.py`  
**Entrypoint:** `POST /intent-test`

- **Purpose:**  
  Simple stub for testing intent detection.  
- **Behavior:**  
  Echoes back the prompt under `{"intent": "test", "prompt": <your text>}`.  
- **Tool:**  
  Pydantic model + FastAPI route.

---

### API Endpoints Overview
- **POST `/ask`** → `RouterAgent`  
- **POST `/intent-test`** → `IntentTestAgent`  
- **GET `/ha/entities`** → raw `get_states()` JSON  
- **POST `/ha/service`** → manual `call_service(domain, service, data)`  
- **GET `/ha/resolve?name=<foo>`** → `{ "entity_id": "<domain.foo>" }`

---
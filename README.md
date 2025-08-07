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
git clone <your-repo-url>
cd your-project
pip install -r requirements.txt
cp .env.example .env
```

### 🔑 3. Configure Environment

Update the copied `.env` with your credentials:

```env
OPENAI_API_KEY=your_openai_key
HOME_ASSISTANT_URL=http://your-ha-instance
HOME_ASSISTANT_TOKEN=your_long_lived_token
JWT_SECRET=your_jwt_secret
EMBEDDING_BACKEND=openai  # or "llama"
# Required when using the LLaMA backend
LLAMA_EMBEDDINGS_MODEL=/path/to/gguf
GPT_SYSTEM_PROMPT="You are a helpful assistant."  # optional system prompt override
```

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

### 📦 Docker Deploy

```bash
docker build -t smart-assistant .
docker run -d -p 8000:8000 --env-file .env smart-assistant
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

Authenticate by POSTing to `/login` with a JSON body containing `username` and
`password`. Valid credentials are supplied via the `LOGIN_USERS` environment
variable as a JSON object mapping usernames to passwords. A successful login
returns both an access token and a refresh token. Access tokens embed the user
ID in the `sub` claim and expire after `JWT_EXPIRE_MINUTES` (default 30 minutes).

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
* `/transcribe/{session_id}` (POST/GET): start or fetch transcription.
* `/ha/entities`, `/ha/service`, `/ha/resolve`: Home Assistant helpers.
* `/health` and `/status`: service status info.
* `/config`: view config.
* `/intent-test`: debug your prompt intent.

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

## Compliance
| Spec Bullet | Patch Lines |
|-------------|-------------|
| 2 | app/router.py L4, app/main.py L9 |
| 4 | app/llama_integration.py L51-L74 |
| 5 | app/router.py L36-L41 |
| 7 | tests/test_imports.py L1-L9, tests/test_no_basicconfig.py L1-L10 |
